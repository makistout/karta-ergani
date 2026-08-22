"""Συμπαγές snapshot Αρχικής (σήμερα + χθες) για τον AI Agent."""

from __future__ import annotations

import time
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from app.card_report import build_card_status_report

_AThens = ZoneInfo("Europe/Athens")
_TODAY_HOME_TTL_SEC = 45.0
_today_home_cache: dict[tuple[Any, ...], tuple[float, dict[str, Any]]] = {}

_OPEN_STATUSES = frozenset({"at_work", "needs_checkout"})


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


def is_open_home_employee(row: dict[str, Any]) -> bool:
    """Ανοιχτή κάρτα: status at_work/needs_checkout ή είσοδος χωρίς έξοδο."""
    status = str(row.get("status") or "").strip()
    if status in _OPEN_STATUSES:
        return True
    return bool(row.get("card_in")) and not bool(row.get("card_out"))


def _store_day_snapshot(
    *,
    store_id: int,
    store_name: str,
    employer_afm: str,
    branch_aa: str,
    date_iso: str,
    open_only: bool = False,
) -> dict[str, Any]:
    report = build_card_status_report(employer_afm, branch_aa, date_iso=date_iso)
    employees = [
        compact_home_employee_row(row)
        for row in (report.get("rows") or [])
        if isinstance(row, dict)
    ]
    if open_only:
        employees = [row for row in employees if is_open_home_employee(row)]
    return {
        "store_id": store_id,
        "name": store_name,
        "summary": report.get("summary") or {},
        "employees": employees,
        "open_count": sum(1 for row in employees if is_open_home_employee(row)),
    }


def build_today_home_context(contexts: list[dict[str, Any]]) -> dict[str, Any]:
    """Αναφορά Αρχικής για σήμερα + χθες (overnight ανοιχτές κάρτες).

    Short TTL cache: sequential chat turns reuse the same snapshot (~45s).
    """
    today_dt = datetime.now(_AThens).date()
    today = today_dt.isoformat()
    yesterday = (today_dt - timedelta(days=1)).isoformat()
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

    cache_key = (today, yesterday, tuple(store_keys))
    cached = _today_home_cache.get(cache_key)
    if cached and (time.monotonic() - cached[0]) < _TODAY_HOME_TTL_SEC:
        return cached[1]

    stores: list[dict[str, Any]] = []
    yesterday_stores: list[dict[str, Any]] = []
    for store_id, employer_afm, branch_aa in store_keys:
        ctx = ctx_by_store[store_id]
        name = str(ctx.get("store_name") or "").strip()
        stores.append(
            _store_day_snapshot(
                store_id=store_id,
                store_name=name,
                employer_afm=employer_afm,
                branch_aa=branch_aa,
                date_iso=today,
            )
        )
        # Χθες: μόνο ανοιχτές (token-cheap) — overnight / κλείσιμο χθεσινών.
        yesterday_stores.append(
            _store_day_snapshot(
                store_id=store_id,
                store_name=name,
                employer_afm=employer_afm,
                branch_aa=branch_aa,
                date_iso=yesterday,
                open_only=True,
            )
        )
    snapshot = {
        "date": today,
        "yesterday_date": yesterday,
        "scope": "today_and_yesterday",
        "description": (
            "Δεδομένα Αρχικής για σήμερα (πλήρη) και χθες (μόνο ανοιχτές κάρτες). "
            "Το χθες καλύπτει overnight βάρδιες: ερωτήσεις/κλείσιμο ανοιχτών καρτών "
            "«χθες» → yesterday / yesterday_date. Μην επινοείς δεδομένα εκτός αυτών."
        ),
        "stores": stores,
        "yesterday": {
            "date": yesterday,
            "note": "Μόνο εργαζόμενοι με ανοιχτή κάρτα την προηγούμενη ημερολογιακή ημέρα.",
            "stores": yesterday_stores,
        },
    }
    _today_home_cache[cache_key] = (time.monotonic(), snapshot)
    stale = [key for key, (ts, _) in _today_home_cache.items() if time.monotonic() - ts >= _TODAY_HOME_TTL_SEC]
    for key in stale:
        _today_home_cache.pop(key, None)
    return snapshot
