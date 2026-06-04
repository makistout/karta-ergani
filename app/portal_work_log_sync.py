"""
Συγχρονισμός πραγματικής απασχόλησης από web portal Ergani
(Ημερολόγιο Πραγματικής Απασχόλησης — WTO/Workcard/DailyWorkTimesSearch.aspx).
"""

from __future__ import annotations

import re
from datetime import datetime
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin

import requests

from app.date_util import iso_to_ergani_dates
from app.ergani_parse import portal_rows_to_work_log_items
from app.portal_schedule_sync import (
    REQUEST_TIMEOUT,
    _asp_hidden,
    _extract_aspnet_form_data,
    _has_next_grid_page,
    _login_session,
    _pick_pararthma,
    _portal_base,
)
from app.repo_entities import upsert_employee_by_afm
from app.repo_work_log import replace_work_log_for_day

DAILY_WORK_TIMES_PATH = "WTO/Workcard/DailyWorkTimesSearch.aspx"
GRID_EVENT_TARGET = (
    "ctl00$ctl00$ContentHolder$ContentHolder$DailyWorkTimesSearchControl"
    "$DailyWorkTimesGridControl$Grid$Grid"
)
MAX_GRID_PAGES = 80


class _FormParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.forms: list[dict] = []
        self._cur: dict | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        ad = {k: v or "" for k, v in attrs}
        if tag == "form":
            self._cur = {"action": ad.get("action", ""), "method": ad.get("method", "get").lower(), "inputs": []}
        elif self._cur is not None and tag == "input":
            self._cur["inputs"].append(ad)
        elif self._cur is not None and tag == "select":
            self._cur["inputs"].append({"tag": "select", **ad})

    def handle_endtag(self, tag: str) -> None:
        if tag == "form" and self._cur is not None:
            self.forms.append(self._cur)
            self._cur = None


def _find_search_form(html: str) -> dict | None:
    p = _FormParser()
    p.feed(html)
    for f in p.forms:
        if "DailyWorkTimesSearchControl" in " ".join(
            i.get("name") or "" for i in f.get("inputs", [])
        ):
            return f
        if len(f.get("inputs", [])) > 8:
            return f
    return p.forms[0] if p.forms else None


def _parse_grid_rows(html: str) -> list[list[str]]:
    rows: list[list[str]] = []
    for tr in re.finditer(r"<tr[^>]*>(.*?)</tr>", html, re.I | re.S):
        chunk = tr.group(1)
        if "MovableElement" not in chunk or "Page$Next" in chunk:
            continue
        cells = [
            re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", td_m.group(1))).strip()
            for td_m in re.finditer(
                r'<td class="MovableElement"[^>]*>(.*?)</td>', chunk, re.I | re.S
            )
        ]
        if len(cells) < 7:
            continue
        if not re.fullmatch(r"\d{8,11}", cells[1]):
            continue
        rows.append(cells[:7])
    return rows


def _collect_all_grid_rows(session: requests.Session, start_url: str, first_html: str) -> list[list[str]]:
    all_rows = _parse_grid_rows(first_html)
    html = first_html
    url = start_url
    pages = 1
    while _has_next_grid_page(html) and pages < MAX_GRID_PAGES:
        fp = _FormParser()
        fp.feed(html)
        action = urljoin(url, fp.forms[0].get("action") or url) if fp.forms else url
        data = _extract_aspnet_form_data(html, include_text=True)
        data["__EVENTTARGET"] = GRID_EVENT_TARGET
        data["__EVENTARGUMENT"] = "Page$Next"
        for key in list(data.keys()):
            if key.endswith("$SearchControlSearchButton"):
                del data[key]
        r = session.post(action, data=data, timeout=REQUEST_TIMEOUT, allow_redirects=True)
        if "error.aspx" in r.url.lower() or "Σφάλμα" in (r.text[:2000]):
            break
        page_rows = _parse_grid_rows(r.text)
        if not page_rows:
            break
        all_rows.extend(page_rows)
        html, url = r.text, r.url
        pages += 1
    return all_rows


def _open_daily_work_times(session: requests.Session, portal_base: str) -> tuple[str, str]:
    r = session.get(urljoin(portal_base, DAILY_WORK_TIMES_PATH), timeout=REQUEST_TIMEOUT)
    if "DailyWorkTimesSearchControl" not in r.text:
        raise RuntimeError("Δεν φορτώθηκε η σελίδα Ημερολογίου Πραγματικής Απασχόλησης")
    return r.text, r.url


def _search_day(
    session: requests.Session,
    page_html: str,
    page_url: str,
    ctx: dict[str, Any],
    work_date: str,
) -> list[list[str]]:
    form = _find_search_form(page_html)
    if not form:
        raise RuntimeError("Δεν βρέθηκε φόρμα αναζήτησης πραγματικής απασχόλησης")

    data = _asp_hidden(form)
    branch_aa = str(ctx.get("branch_aa") or "0").strip()
    par_key = (
        "ctl00$ctl00$ContentHolder$ContentHolder$DailyWorkTimesSearchControl"
        "$PararthmaSelection$PararthmaListEdit"
    )
    data[par_key] = _pick_pararthma(page_html, branch_aa)
    data["ctl00$ctl00$ContentHolder$ContentHolder$DailyWorkTimesSearchControl$AfmEdit"] = ""
    data["ctl00$ctl00$ContentHolder$ContentHolder$DailyWorkTimesSearchControl$EponimoBox"] = ""
    data["ctl00$ctl00$ContentHolder$ContentHolder$DailyWorkTimesSearchControl$NameBox"] = ""
    data["ctl00_ctl00_ContentHolder_ContentHolder_DailyWorkTimesSearchControl_DateFromEdit"] = work_date
    data["ctl00_ctl00_ContentHolder_ContentHolder_DailyWorkTimesSearchControl_DateToEdit"] = work_date
    data[
        "ctl00$ctl00$ContentHolder$ContentHolder$DailyWorkTimesSearchControl$SearchControlSearchButton"
    ] = "Αναζήτηση"

    action = urljoin(page_url, form.get("action") or page_url)
    r = session.post(action, data=data, timeout=REQUEST_TIMEOUT, allow_redirects=True)
    if "error.aspx" in r.url.lower():
        raise RuntimeError(f"Σφάλμα portal κατά την αναζήτηση για {work_date}")

    return _collect_all_grid_rows(session, r.url, r.text)


def sync_work_log_from_portal(
    ctx: dict[str, Any],
    from_iso: str | None = None,
    to_iso: str | None = None,
    *,
    max_days: int = 31,
) -> dict[str, Any]:
    if not from_iso:
        from_iso = datetime.today().strftime("%Y-%m-%d")
    to_iso = to_iso or from_iso
    dates = iso_to_ergani_dates(from_iso, to_iso, max_days)
    employer_afm = str(ctx["employer_afm"]).strip()
    branch_aa = str(ctx.get("branch_aa") or "0").strip()

    portal_base = _portal_base(ctx)
    try:
        session = _login_session(ctx)
        page_html, page_url = _open_daily_work_times(session, portal_base)
    except (requests.RequestException, ValueError, RuntimeError) as ex:
        return {
            "success": False,
            "detail": str(ex),
            "count": 0,
            "days_synced": 0,
            "source": "portal",
            "portal_base": portal_base,
        }

    total = 0
    errors: list[str] = []
    for wd in dates:
        try:
            r_reload = session.get(page_url, timeout=REQUEST_TIMEOUT)
            page_html = r_reload.text
            page_url = r_reload.url
            grid_rows = _search_day(session, page_html, page_url, ctx, wd)
            items = portal_rows_to_work_log_items(grid_rows, default_work_date=wd)
            seen_afm: set[str] = set()
            for it in items:
                afm = (it.get("employee_afm") or "").strip()
                if not afm or afm in seen_afm:
                    continue
                seen_afm.add(afm)
                upsert_employee_by_afm(
                    afm,
                    it.get("eponymo"),
                    it.get("onoma"),
                )
            n = replace_work_log_for_day(employer_afm, branch_aa, wd, items)
            total += n
        except (requests.RequestException, ValueError, RuntimeError) as ex:
            errors.append(f"{wd}: {ex}")

    ok = len(errors) < len(dates)
    single = len(dates) == 1
    return {
        "success": ok,
        "detail": (
            f"{total} εγγραφές portal ({len(dates)} ημέρες)"
            + (f" — {len(errors)} αποτυχίες" if errors else "")
        ),
        "work_date": dates[0] if single else None,
        "work_dates": dates,
        "days_synced": len(dates) - len(errors),
        "count": total,
        "errors": errors[:8],
        "source": "portal",
        "portal_base": portal_base,
    }
