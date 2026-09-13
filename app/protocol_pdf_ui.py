"""Κοινή λογική για σύνδεσμο PDF πρωτοκόλλου στο UI (εκτός σελίδας /ui/protocols)."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import quote

from app.portal_protocol_pdf_match import (
    find_protocol_pdf_path,
    index_protocol_pdfs_for_range,
)
from app.repo_ergani_protocol import get_latest_protocol_by_code
from app.telegram_punch_service import ergani_date_to_iso


def normalize_protocol_code(value: Any) -> str:
    s = str(value or "").strip().upper()
    if not s:
        return ""
    return (
        s.replace("KE", "ΚΕ")
        .replace("OP", "ΟΡ")
        .replace("ΟΠ", "ΟΡ")[:128]
    )


def protocol_pdf_api_url(protocol: str) -> str:
    code = normalize_protocol_code(protocol)
    if not code:
        return ""
    return f"/api/protocols/by-code/pdf?protocol={quote(code, safe='')}"


def _add_days_iso(day_iso: str, days: int) -> str:
    try:
        return (date.fromisoformat(str(day_iso)[:10]) + timedelta(days=days)).isoformat()
    except ValueError:
        return str(day_iso)[:10]


def _iso_bounds_from_work_log_rows(
    rows: list[dict[str, Any]],
    *,
    from_iso: str | None = None,
    to_iso: str | None = None,
) -> tuple[str, str]:
    dates: list[str] = []
    if from_iso:
        dates.append(str(from_iso)[:10])
    if to_iso:
        dates.append(str(to_iso)[:10])
    for row in rows:
        iso = ergani_date_to_iso(str(row.get("work_date") or ""))
        if iso:
            dates.append(iso)
    if not dates:
        today = datetime.now().date().isoformat()
        return today, today
    start = min(dates)
    end = max(dates)
    # Overnight έξοδοι: PDF στον φάκελο D+1.
    return start, _add_days_iso(end, 1)


def _mark_card_meta(meta: Any, pdf_set: set[str]) -> None:
    if not isinstance(meta, dict):
        return
    proto = normalize_protocol_code(meta.get("protocol"))
    if not proto:
        meta["protocol_has_pdf"] = False
        meta.pop("protocol_pdf_url", None)
        return
    has = proto in pdf_set
    meta["protocol_has_pdf"] = has
    if has:
        meta["protocol_pdf_url"] = protocol_pdf_api_url(proto)
    else:
        meta.pop("protocol_pdf_url", None)
    prev = meta.get("previous_events")
    if isinstance(prev, list):
        for ev in prev:
            _mark_card_meta(ev, pdf_set)


def enrich_work_log_rows_with_protocol_pdf(
    rows: list[dict[str, Any]],
    *,
    employer_afm: str,
    branch_aa: str,
    from_iso: str | None = None,
    to_iso: str | None = None,
) -> list[dict[str, Any]]:
    """Σημαίες has_pdf / pdf_url για protocol_from/to και card_db_*."""
    if not rows:
        return rows
    start, end = _iso_bounds_from_work_log_rows(
        rows, from_iso=from_iso, to_iso=to_iso
    )
    pdf_set = index_protocol_pdfs_for_range(
        employer_afm, branch_aa, start, end
    )
    for row in rows:
        for col, flag, url_key in (
            ("protocol_from", "protocol_from_has_pdf", "protocol_from_pdf_url"),
            ("protocol_to", "protocol_to_has_pdf", "protocol_to_pdf_url"),
        ):
            proto = normalize_protocol_code(row.get(col))
            has = bool(proto) and proto in pdf_set
            row[flag] = has
            if has:
                row[url_key] = protocol_pdf_api_url(proto)
            else:
                row.pop(url_key, None)
        _mark_card_meta(row.get("card_db_in"), pdf_set)
        _mark_card_meta(row.get("card_db_out"), pdf_set)
        # Αν το protocol ήρθε μόνο από portal στο meta χωρίς has_pdf από card:
        for meta_key, proto_col, flag in (
            ("card_db_in", "protocol_from", "protocol_from_has_pdf"),
            ("card_db_out", "protocol_to", "protocol_to_has_pdf"),
        ):
            meta = row.get(meta_key)
            if not isinstance(meta, dict):
                continue
            if meta.get("protocol_has_pdf"):
                continue
            proto = normalize_protocol_code(row.get(proto_col) or meta.get("protocol"))
            if proto and proto in pdf_set:
                meta["protocol"] = meta.get("protocol") or proto
                meta["protocol_has_pdf"] = True
                meta["protocol_pdf_url"] = protocol_pdf_api_url(proto)
                row[flag] = True
                row[f"{proto_col}_pdf_url"] = meta["protocol_pdf_url"]
    return rows


def _submit_day_iso(row: dict[str, Any]) -> str:
    raw = str(row.get("submit_at") or "").strip()
    if raw:
        return raw[:10]
    text = str(row.get("submit_date_text") or "").strip()
    if len(text) >= 10 and text[2] == "/" and text[5] == "/":
        d, m, y = text[:2], text[3:5], text[6:10]
        return f"{y}-{m}-{d}"
    return ""


def resolve_protocol_pdf_path_for_store(
    *,
    store_id: int,
    employer_afm: str,
    branch_aa: str,
    protocol: str,
    search_days: int = 120,
) -> tuple[Path | None, dict[str, Any] | None]:
    """Βρίσκει τοπικό PDF για αριθμό πρωτοκόλλου στο ενεργό κατάστημα."""
    code = normalize_protocol_code(protocol)
    if not code:
        return None, None
    row = get_latest_protocol_by_code(int(store_id), code)
    if row:
        day_iso = _submit_day_iso(row)
        if day_iso:
            path = find_protocol_pdf_path(
                str(row.get("employer_afm") or employer_afm or ""),
                str(row.get("branch_aa") or branch_aa or "0"),
                day_iso,
                code,
            )
            if path is not None and path.is_file():
                return path, row

    end = date.today()
    start = end - timedelta(days=max(1, int(search_days)))
    day = start
    while day <= end:
        path = find_protocol_pdf_path(
            employer_afm, branch_aa, day.isoformat(), code
        )
        if path is not None and path.is_file():
            return path, row
        day += timedelta(days=1)
    return None, row
