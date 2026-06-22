"""Κανόνες ειδοποίησης τύπου 2 — τρέχουσα ημέρα."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from app.work_card_payload import tz_athens

TODAY_NOTIFY_KINDS = frozenset(
    {
        "exit_without_entry",
        "late_check_in",
        "missing_exit_8h",
        "rest_with_card",
        "rest_day",
        "early_card",
        "no_schedule_work",
        "no_schedule",
    }
)

KIND_LABELS = {
    "exit_without_entry": "εξόδος χωρίς είσοδο",
    "late_check_in": "καθυστέρηση εισόδου (>10' από ωράριο)",
    "missing_exit_8h": "έλλειψη εξόδου (>8 ώρες από είσοδο)",
    "rest_with_card": "ρεπό/ανάπαυση με καταγραφή εργασίας",
    "rest_day": "ημέρα ρεπό/ανάπαυση",
    "early_card": "κάρτα/πραγματική ≥1 ώρα πριν το ωράριο",
    "no_schedule_work": "καταγραφή εργασίας χωρίς ψηφιακό ωράριο",
    "no_schedule": "δεν υπάρχει ψηφιακό ωράριο",
}

WTO_DAILY_NOTIFY_KINDS = frozenset()


def _parse_clock_minutes(value: str | None) -> int | None:
    m = re.match(r"^(\d{1,2}):(\d{2})", str(value or "").strip())
    if not m:
        return None
    h, mi = int(m.group(1)), int(m.group(2))
    if h < 0 or h > 23 or mi < 0 or mi > 59:
        return None
    return h * 60 + mi


def _elapsed_work_day_minutes(from_min: int, to_min: int) -> int:
    elapsed = to_min - from_min
    if elapsed < 0:
        elapsed += 24 * 60
    return elapsed


def _schedule_start_minutes(row: dict[str, Any]) -> int | None:
    sched = row.get("schedule")
    if isinstance(sched, dict) and sched.get("hour_from"):
        parsed = _parse_clock_minutes(str(sched.get("hour_from")))
        if parsed is not None:
            return parsed
    label = str(row.get("schedule_label") or "").strip()
    if not label or label == "—" or re.search(r"ρεπο|ανάπαυση", label, re.I):
        return None
    parts = [p.strip() for p in label.split("·") if p.strip()]
    last = parts[-1] if parts else label
    match = re.search(r"(\d{1,2}:\d{2}(?::\d{2})?)\s*[–\-]", last)
    if match:
        return _parse_clock_minutes(match.group(1))
    return None


def _today_ergani(now: datetime | None = None) -> str:
    dt = now or datetime.now(tz_athens())
    return dt.strftime("%d/%m/%Y")


def _today_iso(now: datetime | None = None) -> str:
    dt = now or datetime.now(tz_athens())
    return dt.strftime("%Y-%m-%d")


def ergani_date_to_iso(work_date: str) -> str:
    s = (work_date or "").strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s[:10] if fmt == "%Y-%m-%d" else s, fmt).strftime(
                "%Y-%m-%d"
            )
        except ValueError:
            continue
    return s[:10]


def resolve_today_notify_kind(
    row: dict[str, Any],
    *,
    now: datetime | None = None,
) -> str | None:
    """Επιστρέφει notify_kind ή None."""
    dt = now or datetime.now(tz_athens())
    wd_iso = ergani_date_to_iso(str(row.get("work_date") or ""))
    if not wd_iso or wd_iso != _today_iso(dt):
        return None
    active = row.get("employee_active")
    if active is False or active == 0 or active == "0":
        return None

    hf = str(row.get("hour_from") or "").strip()
    ht = str(row.get("hour_to") or "").strip()
    now_min = _parse_clock_minutes(dt.strftime("%H:%M"))
    if now_min is None:
        return None

    if not hf and ht:
        return "exit_without_entry"

    sched_start = _schedule_start_minutes(row)
    if not hf and sched_start is not None:
        if _elapsed_work_day_minutes(sched_start, now_min) >= 10:
            return "late_check_in"

    if hf and not ht:
        start_min = _parse_clock_minutes(hf)
        if start_min is not None and _elapsed_work_day_minutes(start_min, now_min) >= 8 * 60:
            return "missing_exit_8h"

    return None


def card_action_for_today_kind(
    kind: str,
    *,
    schedule_hour_from: str | None = None,
    hour_from: str | None = None,
) -> dict[str, str]:
    k = (kind or "").strip()
    if k in ("exit_without_entry", "late_check_in"):
        rt = (schedule_hour_from or "").strip()
        return {"card_event": "check_in", "retro_time": rt}
    if k == "missing_exit_8h":
        return {"card_event": "check_out", "retro_time": ""}
    return {"card_event": "check_in", "retro_time": ""}


def today_wto_daily_eligible(notify_kind: str) -> bool:
    return (notify_kind or "").strip() in WTO_DAILY_NOTIFY_KINDS


def today_leave_eligible(
    notify_kind: str,
    *,
    schedule_hour_from: str | None = None,
    hour_from: str | None = None,
    hour_to: str | None = None,
) -> bool:
    """Άδεια μόνο όταν λείπει κάρτα/πραγματική είσοδος ενώ υπάρχει ψηφ. ωράριο."""
    if (notify_kind or "").strip() != "late_check_in":
        return False
    if str(hour_from or "").strip() or str(hour_to or "").strip():
        return False
    return bool(str(schedule_hour_from or "").strip())
