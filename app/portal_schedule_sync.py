"""
Συγχρονισμός ψηφιακού ωραρίου από web portal Ergani
(Τρέχουσα Κατάσταση — Mitroa/ErgazomenosWorkingSearch.aspx).
"""

from __future__ import annotations

import re
from datetime import datetime
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin

import requests

from app.date_util import iso_to_ergani_dates
from app.ergani_parse import portal_rows_to_schedule_items
from app.karta_log import KartaLogger, logger_for_store
from app.portal_form_util import set_portal_dates
from app.repo_entities import upsert_employee_by_afm
from app.repo_schedule import replace_schedule_for_day

_SCHEDULE_CTRL = (
    "ctl00$ctl00$ContentHolder$ContentHolder$ErgazomenosWorkingSearchControl"
)
_SCHEDULE_DATE_FROM_FALLBACK = (
    f"{_SCHEDULE_CTRL}$DateFromEdit",
    "ctl00_ctl00_ContentHolder_ContentHolder_ErgazomenosWorkingSearchControl_DateFromEdit",
)
_SCHEDULE_DATE_TO_FALLBACK = (
    f"{_SCHEDULE_CTRL}$DateToEdit",
    "ctl00_ctl00_ContentHolder_ContentHolder_ErgazomenosWorkingSearchControl_DateToEdit",
)

# Προεπιλογή παραγωγή — πραγματικό URL από ctx["portal_base_url"] / ergani_env
PORTAL_BASE = "https://eservices.yeka.gr/"
CURRENT_STATUS_PATH = "Mitroa/ErgazomenosWorkingSearch.aspx"
GRID_EVENT_TARGET = (
    "ctl00$ctl00$ContentHolder$ContentHolder$ErgazomenosWorkingSearchControl"
    "$ErgazomenosWorkingGridControl$Grid$Grid"
)
MAX_GRID_PAGES = 80
REQUEST_TIMEOUT = 90


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


def _asp_hidden(form: dict) -> dict[str, str]:
    out: dict[str, str] = {}
    for inp in form.get("inputs") or []:
        name = inp.get("name") or ""
        if name:
            out[name] = inp.get("value") or ""
    return out


def _find_login_form(html: str) -> dict | None:
    p = _FormParser()
    p.feed(html)
    for f in p.forms:
        names = {i.get("name") for i in f.get("inputs", [])}
        if "ctl00$ctl00$ContentHolder$ContentHolder$SiteLogin$UserName" in names:
            return f
    return p.forms[0] if p.forms else None


def _find_search_form(html: str) -> dict | None:
    p = _FormParser()
    p.feed(html)
    for f in p.forms:
        if "ErgazomenosWorkingSearchControl" in " ".join(
            i.get("name") or "" for i in f.get("inputs", [])
        ):
            return f
        if len(f.get("inputs", [])) > 8:
            return f
    return p.forms[0] if p.forms else None


def _extract_aspnet_form_data(html: str, *, include_text: bool = True) -> dict[str, str]:
    p = _FormParser()
    p.feed(html)
    form = p.forms[0] if p.forms else None
    if not form:
        data: dict[str, str] = {}
        for name in ("__VIEWSTATE", "__VIEWSTATEGENERATOR", "__VIEWSTATEENCRYPTED", "__EVENTVALIDATION"):
            m = re.search(rf'name="{name}"[^>]*value="([^"]*)"', html, re.I)
            if m:
                data[name] = m.group(1)
        return data
    data = _asp_hidden(form)
    for inp in form.get("inputs", []):
        name = inp.get("name") or ""
        if not name or name in data:
            continue
        itype = (inp.get("type") or "").lower()
        if itype in ("hidden",) or (include_text and itype == "text"):
            data[name] = inp.get("value") or ""
    return data


def _has_next_grid_page(html: str) -> bool:
    if "Page$Next" not in html and "Page&#36;Next" not in html:
        return False
    return bool(
        re.search(r"__doPostBack\([^)]*Page(?:\$|&#36;)Next", html, re.I)
        or re.search(r"['\"&#39;]Page(?:\$|&#36;)Next['\"&#39;]", html, re.I)
    )


def _pick_pararthma(html: str, branch_aa: str) -> str:
    aa = str(branch_aa or "0").strip()
    for m in re.finditer(r'<option[^>]+value="([^"]*)"[^>]*>([^<]+)</option>', html, re.I):
        val, label = m.group(1), m.group(2)
        if val == aa or label.strip().startswith(f"{aa} -"):
            return val
    for m in re.finditer(r'<option[^>]+value="(\d+)"', html):
        if m.group(1) != "":
            return m.group(1)
    return aa or "0"


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
        if len(cells) < 8:
            continue
        if not re.fullmatch(r"\d{8,11}", cells[1]):
            continue
        rows.append(cells[:9])
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


def _portal_base(ctx: dict[str, Any]) -> str:
    from app.ergani_env import portal_base_from_ctx

    return portal_base_from_ctx(ctx)


def _login_session(ctx: dict[str, Any]) -> requests.Session:
    from app.ergani_env import portal_login_credentials

    portal_base = _portal_base(ctx)
    user, pwd, usertype = portal_login_credentials(ctx)
    if not user or not pwd:
        raise ValueError("Λείπουν διαπιστευτήρια portal (username/password) στο κατάστημα")

    session = requests.Session()
    session.headers.update({
        "User-Agent": "karta-ergani/1.0",
        "Accept-Language": "el-GR,el;q=0.9",
    })
    r0 = session.get(portal_base, timeout=REQUEST_TIMEOUT)
    form = _find_login_form(r0.text)
    if not form:
        raise RuntimeError("Δεν βρέθηκε φόρμα σύνδεσης Ergani portal")

    data = _asp_hidden(form)
    data["ctl00$ctl00$ContentHolder$ContentHolder$SiteLogin$UserName"] = user
    data["ctl00$ctl00$ContentHolder$ContentHolder$SiteLogin$Password"] = pwd
    data["ctl00$ctl00$ContentHolder$ContentHolder$SiteLogin$Login"] = "Είσοδος"
    # Χωρίς «Σύνδεση με κωδικούς ΕΡΓΑΝΗ» — το checkbox αποτυγχάνει για EFKA και εξωτερικό web user.

    action = urljoin(r0.url, form.get("action") or "")
    r1 = session.post(action, data=data, timeout=REQUEST_TIMEOUT, allow_redirects=True)
    if "text-danger" in r1.text or "SiteLogin$UserName" in r1.text:
        raise RuntimeError("Αποτυχία σύνδεσης Ergani portal — ελέγξτε διαπιστευτήρια καταστήματος")
    if "Default.aspx" in r1.text:
        session.get(urljoin(r1.url, "Default.aspx"), timeout=REQUEST_TIMEOUT)
    return session


def _open_current_status(session: requests.Session, portal_base: str) -> tuple[str, str]:
    r = session.get(urljoin(portal_base, CURRENT_STATUS_PATH), timeout=REQUEST_TIMEOUT)
    if "ErgazomenosWorkingSearchControl" not in r.text:
        raise RuntimeError("Δεν φορτώθηκε η σελίδα Τρέχουσας Κατάστασης Ψηφιακής Οργάνωσης")
    return r.text, r.url


def _search_schedule(
    session: requests.Session,
    page_html: str,
    page_url: str,
    ctx: dict[str, Any],
    date_from: str,
    date_to: str | None = None,
) -> list[list[str]]:
    """Αναζήτηση ωραρίου portal (μία ημέρα ή διάστημα Από–Έως)."""
    date_to = date_to or date_from
    form = _find_search_form(page_html)
    if not form:
        raise RuntimeError("Δεν βρέθηκε φόρμα αναζήτησης ωραρίου")

    data = _extract_aspnet_form_data(page_html, include_text=True)
    branch_aa = str(ctx.get("branch_aa") or "0").strip()
    data[f"{_SCHEDULE_CTRL}$PararthmaSelection$PararthmaListEdit"] = _pick_pararthma(
        page_html, branch_aa
    )
    data[f"{_SCHEDULE_CTRL}$AfmEdit"] = ""
    data[f"{_SCHEDULE_CTRL}$EponimoBox"] = ""
    data[f"{_SCHEDULE_CTRL}$NameBox"] = ""
    set_portal_dates(
        data,
        page_html,
        date_from,
        date_to,
        fallback_from=_SCHEDULE_DATE_FROM_FALLBACK,
        fallback_to=_SCHEDULE_DATE_TO_FALLBACK,
    )
    data[f"{_SCHEDULE_CTRL}$SearchControlSearchButton"] = "Αναζήτηση"

    action = urljoin(page_url, form.get("action") or page_url)
    r = session.post(action, data=data, timeout=REQUEST_TIMEOUT, allow_redirects=True)
    if "error.aspx" in r.url.lower():
        raise RuntimeError(
            f"Σφάλμα portal κατά την αναζήτηση για {date_from} – {date_to}"
        )

    return _collect_all_grid_rows(session, r.url, r.text)


def _persist_schedule_items(
    ctx: dict[str, Any],
    work_dates: list[str],
    items: list[dict[str, Any]],
) -> int:
    employer_afm = str(ctx["employer_afm"]).strip()
    branch_aa = str(ctx.get("branch_aa") or "0").strip()
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
        total += replace_schedule_for_day(employer_afm, branch_aa, wd, deduped)
    return total


def _schedule_sync_result(
    *,
    dates: list[str],
    total: int,
    errors: list[str],
    days_synced: int,
    portal_base: str,
    log: KartaLogger,
) -> dict[str, Any]:
    ok = days_synced > 0 and len(errors) < len(dates)
    single = len(dates) == 1
    detail = (
        f"{total} εγγραφές portal ({len(dates)} ημέρες)"
        + (f" — {len(errors)} αποτυχίες" if errors else "")
    )
    log.info(
        "Ολοκλήρωση συγχρονισμού ωραρίου",
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
        "portal_base": portal_base,
    }


def iter_schedule_sync_events(
    ctx: dict[str, Any],
    from_iso: str | None = None,
    to_iso: str | None = None,
    *,
    max_days: int = 31,
    run_id: str | None = None,
) -> Any:
    """Generator NDJSON events: progress, day_ok, day_err, done, error."""
    if not from_iso:
        from_iso = datetime.today().strftime("%Y-%m-%d")
    to_iso = to_iso or from_iso
    dates = iso_to_ergani_dates(from_iso, to_iso, max_days)
    log = logger_for_store("schedule_sync", ctx, run_id=run_id)
    finalize_run = run_id is None
    portal_base = _portal_base(ctx)

    log.info(
        "Έναρξη συγχρονισμού ωραρίου",
        from_iso=from_iso,
        to_iso=to_iso,
        days=len(dates),
        portal_base=portal_base,
    )
    yield {
        "event": "progress",
        "message": "Σύνδεση στο portal Ergani (ψηφιακό ωράριο)…",
        "step": 0,
        "total": len(dates),
    }

    try:
        session = _login_session(ctx)
        page_html, page_url = _open_current_status(session, portal_base)
        log.info("Σύνδεση portal (ψηφιακό ωράριο) — OK")
    except (requests.RequestException, ValueError, RuntimeError) as ex:
        log.error(f"Αποτυχία σύνδεσης portal: {ex}")
        yield {
            "event": "error",
            "message": str(ex),
            "logs": log.tail(100),
        }
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

    for i, wd in enumerate(dates):
        msg = f"Ψηφιακό ωράριο: ενημέρωση {wd} ({i + 1}/{len(dates)})…"
        log.info(msg, work_date=wd, step=i + 1, total=len(dates))
        yield {
            "event": "progress",
            "message": msg,
            "step": i + 1,
            "total": len(dates),
            "work_date": wd,
        }
        try:
            r_reload = session.get(page_url, timeout=REQUEST_TIMEOUT)
            page_html = r_reload.text
            page_url = r_reload.url
            log.info(f"Ψηφιακό ωράριο: αναζήτηση στο portal για {wd}", work_date=wd)
            grid_rows = _search_schedule(session, page_html, page_url, ctx, wd, wd)
            items = portal_rows_to_schedule_items(grid_rows, default_work_date=wd)
            n = _persist_schedule_items(ctx, [wd], items)
            total += n
            days_synced += 1
            log.info(f"Ψηφιακό ωράριο: αποθηκεύτηκαν {n} εγγραφές για {wd}", work_date=wd, count=n)
            yield {
                "event": "day_ok",
                "message": f"Ψηφιακό ωράριο: {wd} — {n} εγγραφές",
                "work_date": wd,
                "count": n,
            }
        except (requests.RequestException, ValueError, RuntimeError) as ex:
            err = f"{wd}: {ex}"
            errors.append(err)
            log.error(str(ex), work_date=wd)
            yield {"event": "day_err", "message": err, "work_date": wd}

    result = _schedule_sync_result(
        dates=dates,
        total=total,
        errors=errors,
        days_synced=days_synced,
        portal_base=portal_base,
        log=log,
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

        repo_store.touch_schedule_sync(int(ctx["id"]))
    yield {
        "event": "done",
        "success": result["success"],
        "sync": result,
        "message": result["detail"],
        "logs": result.get("logs"),
        "error": None if result["success"] else result["detail"],
    }


def sync_schedule_from_portal(
    ctx: dict[str, Any],
    from_iso: str | None = None,
    to_iso: str | None = None,
    *,
    max_days: int = 31,
) -> dict[str, Any]:
    """Parse portal ανά ημέρα — αποθήκευση karta_schedule (χωρίς streaming)."""
    portal_base = _portal_base(ctx)
    for ev in iter_schedule_sync_events(
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
