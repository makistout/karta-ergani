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
from app.karta_log import KartaLogger, logger_for_store
from app.portal_excel import fetch_work_log_rows_via_excel
from app.portal_form_util import set_portal_dates
from app.portal_schedule_sync import (
    REQUEST_TIMEOUT,
    _extract_aspnet_form_data,
    _has_next_grid_page,
    _login_session,
    _pick_pararthma,
    _portal_base,
)

_WORKLOG_CTRL = "ctl00$ctl00$ContentHolder$ContentHolder$DailyWorkTimesSearchControl"
_WORKLOG_DATE_FROM_FALLBACK = (
    f"{_WORKLOG_CTRL}$DateFromEdit",
    "ctl00_ctl00_ContentHolder_ContentHolder_DailyWorkTimesSearchControl_DateFromEdit",
)
_WORKLOG_DATE_TO_FALLBACK = (
    f"{_WORKLOG_CTRL}$DateToEdit",
    "ctl00_ctl00_ContentHolder_ContentHolder_DailyWorkTimesSearchControl_DateToEdit",
)
from app.repo_entities import upsert_employee_by_afm
from app.repo_work_log import delete_work_log_without_active_employment
from app.repo_work_log import replace_work_log_for_day
from app.work_card_payload import norm_afm

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


def _search_work_log(
    session: requests.Session,
    page_html: str,
    page_url: str,
    ctx: dict[str, Any],
    date_from: str,
    date_to: str | None = None,
) -> tuple[list[list[str]], str]:
    """Αναζήτηση πραγματικής — επιστρέφει (grid_rows, source: excel|html)."""
    date_to = date_to or date_from
    form = _find_search_form(page_html)
    if not form:
        raise RuntimeError("Δεν βρέθηκε φόρμα αναζήτησης πραγματικής απασχόλησης")

    data = _extract_aspnet_form_data(page_html, include_text=True)
    branch_aa = str(ctx.get("branch_aa") or "0").strip()
    data[f"{_WORKLOG_CTRL}$PararthmaSelection$PararthmaListEdit"] = _pick_pararthma(
        page_html, branch_aa
    )
    data[f"{_WORKLOG_CTRL}$AfmEdit"] = ""
    data[f"{_WORKLOG_CTRL}$EponimoBox"] = ""
    data[f"{_WORKLOG_CTRL}$NameBox"] = ""
    set_portal_dates(
        data,
        page_html,
        date_from,
        date_to,
        fallback_from=_WORKLOG_DATE_FROM_FALLBACK,
        fallback_to=_WORKLOG_DATE_TO_FALLBACK,
    )
    data[f"{_WORKLOG_CTRL}$SearchControlSearchButton"] = "Αναζήτηση"

    action = urljoin(page_url, form.get("action") or page_url)
    r = session.post(action, data=data, timeout=REQUEST_TIMEOUT, allow_redirects=True)
    if "error.aspx" in r.url.lower():
        raise RuntimeError(
            f"Σφάλμα portal κατά την αναζήτηση για {date_from} – {date_to}"
        )

    try:
        rows = fetch_work_log_rows_via_excel(
            session, r.text, r.url, grid_event_target=GRID_EVENT_TARGET
        )
        return rows, "excel"
    except Exception:
        rows = _collect_all_grid_rows(session, r.url, r.text)
        if not rows:
            raise RuntimeError(
                f"Δεν βρέθηκαν εγγραφές (ούτε Excel ούτε HTML grid) για {date_from} – {date_to}"
            )
        return rows, "html"


def _active_staff_afms(ctx: dict[str, Any]) -> set[str] | None:
    from app.repo_entities import list_employees_for_employer

    rows = list_employees_for_employer(
        str(ctx["employer_afm"]),
        str(ctx.get("branch_aa") or "0"),
        active_only=True,
    )
    if not rows:
        return None
    return {norm_afm(r["afm"]) for r in rows if r.get("afm")}


def _filter_work_log_items_for_staff(
    ctx: dict[str, Any],
    items: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    staff = _active_staff_afms(ctx)
    if not staff:
        return items
    return [
        it
        for it in items
        if norm_afm(it.get("employee_afm") or "") in staff
    ]


def _persist_work_log_items(
    ctx: dict[str, Any],
    work_dates: list[str],
    items: list[dict[str, Any]],
) -> int:
    employer_afm = str(ctx["employer_afm"]).strip()
    branch_aa = str(ctx.get("branch_aa") or "0").strip()
    items = _filter_work_log_items_for_staff(ctx, items)
    by_day: dict[str, list[dict[str, Any]]] = {}
    for it in items:
        wd = str(it.get("work_date") or "").strip()
        if wd:
            by_day.setdefault(wd, []).append(it)

    total = 0
    for wd in work_dates:
        day_items = by_day.get(wd, [])
        seen_afm: set[str] = set()
        deduped: list[dict[str, Any]] = []
        for it in day_items:
            afm = (it.get("employee_afm") or "").strip()
            if not afm or afm in seen_afm:
                continue
            seen_afm.add(afm)
            upsert_employee_by_afm(afm, it.get("eponymo"), it.get("onoma"))
            deduped.append(it)
        total += replace_work_log_for_day(employer_afm, branch_aa, wd, deduped)
    return total


def _work_log_sync_result(
    *,
    dates: list[str],
    total: int,
    errors: list[str],
    days_synced: int,
    portal_base: str,
    log: KartaLogger,
    fetch_source: str = "excel",
) -> dict[str, Any]:
    ok = days_synced > 0 and len(errors) < len(dates)
    single = len(dates) == 1
    detail = (
        f"{total} εγγραφές portal ({len(dates)} ημέρες, {fetch_source})"
        + (f" — {len(errors)} αποτυχίες" if errors else "")
    )
    log.info(
        "Ολοκλήρωση συγχρονισμού πραγματικής",
        success=ok,
        count=total,
        days_synced=days_synced,
        errors=len(errors),
    )
    return {
        "success": ok,
        "detail": detail,
        "work_date": dates[0] if single else None,
        "work_dates": dates,
        "days_synced": days_synced,
        "count": total,
        "errors": errors[:20],
        "logs": log.tail(100),
        "source": "portal",
        "fetch_source": fetch_source,
        "portal_base": portal_base,
    }


def iter_work_log_sync_events(
    ctx: dict[str, Any],
    from_iso: str | None = None,
    to_iso: str | None = None,
    *,
    max_days: int = 31,
    run_id: str | None = None,
) -> Any:
    if not from_iso:
        from_iso = datetime.today().strftime("%Y-%m-%d")
    to_iso = to_iso or from_iso
    dates = iso_to_ergani_dates(from_iso, to_iso, max_days)
    log = logger_for_store("work_log_sync", ctx, run_id=run_id)
    finalize_run = run_id is None
    portal_base = _portal_base(ctx)

    log.info(
        "Έναρξη συγχρονισμού πραγματικής",
        from_iso=from_iso,
        to_iso=to_iso,
        days=len(dates),
        portal_base=portal_base,
    )
    yield {
        "event": "progress",
        "message": "Σύνδεση στο portal Ergani (πραγματική απασχόληση)…",
        "step": 0,
        "total": len(dates),
    }

    try:
        session = _login_session(ctx)
        page_html, page_url = _open_daily_work_times(session, portal_base)
        log.info("Σύνδεση portal (πραγματική απασχόληση) — OK")
    except (requests.RequestException, ValueError, RuntimeError) as ex:
        log.error(f"Αποτυχία σύνδεσης portal: {ex}")
        yield {"event": "error", "message": str(ex), "logs": log.tail(100)}
        if finalize_run:
            from app import repo_sync_log

            repo_sync_log.finish_run(
                log.run_id,
                status="error",
                message=str(ex),
                result={"success": False, "error": str(ex)},
            )
        return

    total = 0
    errors: list[str] = []
    days_synced = 0
    date_from, date_to = dates[0], dates[-1]
    fetch_source = "excel"

    yield {
        "event": "progress",
        "message": f"Πραγματική απασχόληση: αναζήτηση {date_from} – {date_to}…",
        "step": 1,
        "total": len(dates),
    }
    try:
        log.info(
            f"Πραγματική απασχόληση: αναζήτηση στο portal για {date_from} – {date_to}",
            date_from=date_from,
            date_to=date_to,
        )
        grid_rows, fetch_source = _search_work_log(
            session, page_html, page_url, ctx, date_from, date_to
        )
        log.info(
            f"Πραγματική απασχόληση: {len(grid_rows)} γραμμές από {fetch_source}",
            source=fetch_source,
            count=len(grid_rows),
        )
        items = portal_rows_to_work_log_items(grid_rows, default_work_date=date_from)
        items = _filter_work_log_items_for_staff(ctx, items)
        by_day: dict[str, int] = {}
        for it in items:
            wd = str(it.get("work_date") or "").strip()
            if wd:
                by_day[wd] = by_day.get(wd, 0) + 1

        total = _persist_work_log_items(ctx, dates, items)
        removed = delete_work_log_without_active_employment(
            str(ctx["employer_afm"]),
            str(ctx.get("branch_aa") or "0"),
        )
        if removed:
            log.info(
                f"Αφαιρέθηκαν {removed} εγγραφές πραγματικής εκτός τρέχοντος προσωπικού",
                count=removed,
            )
        for i, wd in enumerate(dates):
            n = by_day.get(wd, 0)
            if n > 0:
                days_synced += 1
            log.info(
                f"Πραγματική απασχόληση: {n} εγγραφές για {wd}",
                work_date=wd,
                count=n,
            )
            yield {
                "event": "day_ok" if n > 0 else "day_skip",
                "message": (
                    f"Πραγματική απασχόληση: {wd} — {n} εγγραφές ({fetch_source})"
                    if n > 0
                    else f"Πραγματική απασχόληση: {wd} — χωρίς εγγραφές"
                ),
                "work_date": wd,
                "count": n,
                "source": fetch_source,
            }
    except (requests.RequestException, ValueError, RuntimeError) as ex:
        err = f"{date_from} – {date_to}: {ex}"
        errors.append(err)
        log.error(str(ex), date_from=date_from, date_to=date_to)
        yield {"event": "day_err", "message": err, "work_date": date_from}

    result = _work_log_sync_result(
        dates=dates,
        total=total,
        errors=errors,
        days_synced=days_synced,
        portal_base=portal_base,
        log=log,
        fetch_source=fetch_source,
    )
    if finalize_run:
        from app import repo_sync_log

        repo_sync_log.finish_run(
            log.run_id,
            status="done" if result["success"] else "error",
            message=result["detail"],
            result=result,
        )
    if result.get("success") and ctx.get("id"):
        from app import repo_store

        repo_store.touch_work_log_sync(int(ctx["id"]))
    yield {
        "event": "done",
        "success": result["success"],
        "sync": result,
        "message": result["detail"],
        "logs": result.get("logs"),
        "error": None if result["success"] else result["detail"],
    }


def sync_work_log_from_portal(
    ctx: dict[str, Any],
    from_iso: str | None = None,
    to_iso: str | None = None,
    *,
    max_days: int = 31,
) -> dict[str, Any]:
    portal_base = _portal_base(ctx)
    for ev in iter_work_log_sync_events(
        ctx, from_iso=from_iso, to_iso=to_iso, max_days=max_days
    ):
        if ev.get("event") == "done":
            return ev.get("sync") or {
                "success": False,
                "detail": ev.get("error") or "Αποτυχία",
                "count": 0,
                "days_synced": 0,
                "source": "portal",
                "portal_base": portal_base,
            }
        if ev.get("event") == "error":
            return {
                "success": False,
                "detail": ev.get("message") or "Αποτυχία",
                "count": 0,
                "days_synced": 0,
                "errors": [],
                "logs": ev.get("logs") or [],
                "source": "portal",
                "portal_base": portal_base,
            }
    return {
        "success": False,
        "detail": "Διακόπηκε ο συγχρονισμός",
        "count": 0,
        "days_synced": 0,
        "source": "portal",
        "portal_base": portal_base,
    }
