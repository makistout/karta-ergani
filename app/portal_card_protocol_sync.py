"""
Συγχρονισμός πρωτοκόλλων χτυπημάτων κάρτας από portal Ergani
(Αναζήτηση δήλωσης προσέλευσης/αποχώρησης — WTO/Workcard/WorkCardSearch.aspx).
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime, timedelta
from typing import Any
from urllib.parse import urljoin

import requests

from app.date_util import format_date_for_ergani
from app.karta_log import KartaLogger, logger_for_store
from app.portal_excel import _parse_xlsx, download_grid_excel
from app.portal_excel_archive import PortalExcelArchive, log_excel_archive_saved
from app.portal_form_util import set_portal_dates
from app.repo_ergani_protocol import (
    parse_card_protocol_export_rows,
    table_missing_message,
    upsert_protocol_rows,
)
from app.portal_schedule_sync import (
    REQUEST_TIMEOUT,
    _extract_aspnet_form_data,
    _find_search_form,
    _login_session,
    _pick_pararthma,
    _portal_base,
)

WORK_CARD_SEARCH_PATH = "WTO/Workcard/WorkCardSearch.aspx"
_CTRL = "ctl00$ctl00$ContentHolder$ContentHolder$WorkCardSearchControl"
_GRID = (
    "ctl00$ctl00$ContentHolder$ContentHolder$WorkCardSearchControl"
    "$WorkCardGridControl$Grid$Grid"
)
_DATE_FROM_FALLBACK = (
    f"{_CTRL}$DateYpobolisFromEdit",
    "ctl00_ctl00_ContentHolder_ContentHolder_WorkCardSearchControl_DateYpobolisFromEdit",
)
_DATE_TO_FALLBACK = (
    f"{_CTRL}$DateYpobolisToEdit",
    "ctl00_ctl00_ContentHolder_ContentHolder_WorkCardSearchControl_DateYpobolisToEdit",
)


def _open_work_card_search(session: requests.Session, portal_base: str) -> tuple[str, str]:
    url = urljoin(portal_base, WORK_CARD_SEARCH_PATH)
    r = session.get(url, timeout=REQUEST_TIMEOUT, allow_redirects=True)
    if r.status_code >= 400:
        raise RuntimeError(f"Αποτυχία φόρτωσης WorkCardSearch — HTTP {r.status_code}")
    if "WorkCardSearchControl" not in r.text:
        raise RuntimeError("Η σελίδα WorkCardSearch δεν φορτώθηκε σωστά")
    return r.text, r.url


def _search_card_protocols_excel(
    session: requests.Session,
    page_html: str,
    page_url: str,
    ctx: dict[str, Any],
    date_from: str,
    date_to: str,
    *,
    run_id: str | None = None,
    log: KartaLogger | None = None,
) -> list[list[str]]:
    form = _find_search_form(page_html)
    if not form:
        raise RuntimeError("Δεν βρέθηκε φόρμα WorkCardSearch")
    data = _extract_aspnet_form_data(page_html, include_text=True)
    branch_aa = str(ctx.get("branch_aa") or "0").strip()
    data[f"{_CTRL}$PararthmaSelection$PararthmaListEdit"] = _pick_pararthma(page_html, branch_aa)
    data[f"{_CTRL}$AfmErgazomenoyEdit"] = ""
    data[f"{_CTRL}$ArProtocolEdit"] = ""
    set_portal_dates(
        data,
        page_html,
        date_from,
        date_to,
        fallback_from=_DATE_FROM_FALLBACK,
        fallback_to=_DATE_TO_FALLBACK,
    )
    data[f"{_CTRL}$SearchControlSearchButton"] = "Αναζήτηση"
    action = urljoin(page_url, form.get("action") or page_url)
    r = session.post(action, data=data, timeout=REQUEST_TIMEOUT, allow_redirects=True)
    if r.status_code >= 400:
        raise RuntimeError(f"Αποτυχία αναζήτησης WorkCardSearch — HTTP {r.status_code}")
    if "error.aspx" in r.url.lower():
        raise RuntimeError("Αποτυχία αναζήτησης WorkCardSearch — error.aspx")

    content, ctype = download_grid_excel(
        session, r.text, r.url, grid_event_target=_GRID
    )
    archive = PortalExcelArchive.for_sync(
        kind="card_protocol",
        ctx=ctx,
        date_from=date_from,
        date_to=date_to,
        run_id=run_id,
    )
    rows = _parse_xlsx(content)
    if archive is not None:
        archive.record_excel(content, ctype, row_count=max(0, len(rows) - 1))
        log_excel_archive_saved(archive, log)

    return rows


def sync_card_protocols_from_portal(
    ctx: dict[str, Any],
    *,
    from_iso: str | None = None,
    to_iso: str | None = None,
    max_days: int = 31,
    run_id: str | None = None,
) -> dict[str, Any]:
    """Συγχρονισμός πρωτοκόλλων κάρτας για διάστημα ημερομηνιών υποβολής."""
    log = logger_for_store("card_protocol_sync", ctx, run_id=run_id)
    store_id = int(ctx["id"])
    employer_afm = str(ctx.get("employer_afm") or "")
    branch_aa = str(ctx.get("branch_aa") or "0").strip() or "0"

    if to_iso:
        end = datetime.strptime(to_iso[:10], "%Y-%m-%d").date()
    else:
        end = datetime.now().date()
    if from_iso:
        start = datetime.strptime(from_iso[:10], "%Y-%m-%d").date()
    else:
        start = end - timedelta(days=max(1, int(max_days)) - 1)
    if start > end:
        start, end = end, start
    days_synced = (end - start).days + 1

    date_from = format_date_for_ergani(start.isoformat())
    date_to = format_date_for_ergani(end.isoformat())
    portal_base = _portal_base(ctx)

    try:
        session = _login_session(ctx)
        page_html, page_url = _open_work_card_search(session, portal_base)
        raw_rows = _search_card_protocols_excel(
            session,
            page_html,
            page_url,
            ctx,
            date_from,
            date_to,
            run_id=log.run_id,
            log=log,
        )
    except Exception as ex:
        msg = str(ex)
        log.error(f"Αποτυχία sync πρωτοκόλλων: {msg}")
        return {"success": False, "detail": msg, "count": 0}

    parsed = parse_card_protocol_export_rows(
        raw_rows,
        employer_afm=employer_afm,
        branch_aa=branch_aa,
    )
    try:
        stats = upsert_protocol_rows(store_id, parsed, sync_run_id=log.run_id)
    except Exception as ex:
        tb_msg = table_missing_message(ex)
        msg = tb_msg or str(ex)
        log.error(f"Αποτυχία αποθήκευσης πρωτοκόλλων: {msg}")
        return {"success": False, "detail": msg, "count": 0}

    try:
        from app import repo_store

        repo_store.touch_protocol_sync(store_id)
    except Exception as ex:
        log.warning(f"Δεν ενημερώθηκε protocol_last_sync_at: {ex}")

    detail = (
        f"{stats['total']} πρωτόκολλα ({stats['inserted']} νέα, {stats['updated']} ενημερώθηκαν) "
        f"για {date_from} – {date_to}"
    )
    log.info(detail, **stats, date_from=date_from, date_to=date_to)
    return {
        "success": True,
        "detail": detail,
        "count": stats["total"],
        "inserted": stats["inserted"],
        "updated": stats["updated"],
        "date_from": date_from,
        "date_to": date_to,
        "days_synced": days_synced,
        "portal_rows": len(raw_rows),
        "parsed_rows": len(parsed),
        "fetch_source": "excel",
    }


def iter_card_protocol_sync_events(
    ctx: dict[str, Any],
    *,
    from_iso: str | None = None,
    to_iso: str | None = None,
    max_days: int = 31,
    run_id: str | None = None,
) -> Iterator[dict[str, Any]]:
    """Generator events για sync πρωτοκόλλων (μία κλήση ανά chunk)."""
    result = sync_card_protocols_from_portal(
        ctx,
        from_iso=from_iso,
        to_iso=to_iso,
        max_days=max_days,
        run_id=run_id,
    )
    if result.get("success"):
        yield {"event": "done", "sync": result, "message": result.get("detail")}
    else:
        yield {"event": "error", "message": result.get("detail") or "Αποτυχία sync πρωτοκόλλων"}
