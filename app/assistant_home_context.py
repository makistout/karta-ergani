"""Συμπαγές snapshot Αρχικής (μόνο σήμερα) για τον AI Agent."""

from __future__ import annotations

import time
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from app.card_report import build_card_status_report

_AThens = ZoneInfo("Europe/Athens")
_TODAY_HOME_TTL_SEC = 45.0
_today_home_cache: dict[tuple[Any, ...], tuple[float, dict[str, Any]]] = {}


def _hm_short(value: str | None) -> str:
    text = str(value or "").strip()
    return text[:5] if text else ""


def _schedule_end(row: dict[str, Any] | None) -> str | None:
    if not row:
        return None
    intervals = row.get("intervals") or []
    ends = [_hm_short(item.get("hour_to")) for item in intervals if isinstance(item, dict)]
    ends = [value for value in ends if value]
    if ends:
        return max(ends)
    end = _hm_short(row.get("hour_to"))
    return end or None


def compact_home_employee_row(row: dict[str, Any]) -> dict[str, Any]:
    """Μία γραμμή Αρχικής — μόνο τα πεδία που χρειάζεται ο AI Agent."""
    sched = row.get("schedule") if isinstance(row.get("schedule"), dict) else {}
    intervals = [
        {"from": _hm_short(item.get("hour_from")), "to": _hm_short(item.get("hour_to"))}
        for item in (sched.get("intervals") or [])
        if isinstance(item, dict) and (_hm_short(item.get("hour_from")) or _hm_short(item.get("hour_to")))
    ]
    card = row.get("card") if isinstance(row.get("card"), dict) else {}
    out: dict[str, Any] = {
        "afm": str(row.get("employee_afm") or "").strip(),
        "name": f"{row.get('eponymo') or ''} {row.get('onoma') or ''}".strip(),
        "status": str(row.get("status") or "").strip(),
    }
    if sched:
        out["schedule_from"] = _hm_short(sched.get("hour_from")) or None
        out["schedule_to"] = _schedule_end(sched)
        if intervals:
            out["intervals"] = intervals
        shift = str(sched.get("shift_type") or "").strip()
        if shift:
            out["shift_type"] = shift
    if card.get("has_check_in"):
        out["card_in"] = str(card.get("check_in") or "").strip() or None
    if card.get("has_check_out"):
        out["card_out"] = str(card.get("check_out") or "").strip() or None
    return {key: value for key, value in out.items() if value not in (None, "", [])}


def build_today_home_context(contexts: list[dict[str, Any]]) -> dict[str, Any]:
    """Αναφορά Αρχικής μόνο για σήμερα, ανά επιτρεπόμενο κατάστημα.

    Short TTL cache: sequential chat turns reuse the same snapshot (~45s).
    """
    today = datetime.now(_AThens).date().isoformat()
    store_keys: list[tuple[int, str, str]] = []
    seen: set[int] = set()
    ctx_by_store: dict[int, dict[str, Any]] = {}
    for ctx in contexts:
        store_id = int(ctx.get("store_id") or 0)
        if not store_id or store_id in seen:
            continue
        employer_afm = str(ctx.get("employer_afm") or "").strip()
        branch_aa = str(ctx.get("branch_aa") or "0").strip() or "0"
        if not employer_afm:
            continue
        seen.add(store_id)
        store_keys.append((store_id, employer_afm, branch_aa))
        ctx_by_store[store_id] = ctx

    cache_key = (today, tuple(store_keys))
    cached = _today_home_cache.get(cache_key)
    if cached and (time.monotonic() - cached[0]) < _TODAY_HOME_TTL_SEC:
        return cached[1]

    stores: list[dict[str, Any]] = []
    for store_id, employer_afm, branch_aa in store_keys:
        ctx = ctx_by_store[store_id]
        report = build_card_status_report(employer_afm, branch_aa, date_iso=today)
        stores.append({
            "store_id": store_id,
            "name": str(ctx.get("store_name") or "").strip(),
            "summary": report.get("summary") or {},
            "employees": [
                compact_home_employee_row(row)
                for row in (report.get("rows") or [])
                if isinstance(row, dict)
            ],
        })
    snapshot = {
        "date": today,
        "scope": "today_only",
        "description": (
            "Δεδομένα Αρχικής μόνο για σήμερα: ονόματα, ψηφιακό ωράριο, "
            "χτυπήματα κάρτας και status. "
            "Χρησιμοποίησέ τα και για απαντήσεις σε ερωτήσεις για σήμερα."
        ),
        "stores": stores,
    }
    _today_home_cache[cache_key] = (time.monotonic(), snapshot)
    # Drop stale keys (different day / stores) so memory stays small.
    stale = [key for key, (ts, _) in _today_home_cache.items() if time.monotonic() - ts >= _TODAY_HOME_TTL_SEC]
    for key in stale:
        _today_home_cache.pop(key, None)
    return snapshot
