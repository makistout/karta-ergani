"""Κανόνες ειδοποίησης τύπου 2 — τρέχουσα ημέρα."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from app.work_card_payload import tz_athens

NOTIFY_GRACE_MINUTES = 10

TODAY_NOTIFY_KINDS = frozenset(
    {
        "exit_without_entry",
        "late_check_in",
        "late_check_out",
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
    "late_check_out": "έλλειψη εξόδου (>10' από αναμενόμενη λήξη)",
    "missing_exit_8h": "έλλειψη εξόδου (>8 ώρες από είσοδο)",
    "rest_with_card": "ρεπό/ανάπαυση με καταγραφή εργασίας",
    "rest_day": "ημέρα ρεπό/ανάπαυση",
    "early_card": "κάρτα/πραγματική ≥1 ώρα πριν το ωράριο",
    "no_schedule_work": "καταγραφή εργασίας χωρίς ψηφιακό ωράριο",
    "no_schedule": "δεν υπάρχει ψηφιακό ωράριο",
}

WTO_DAILY_NOTIFY_KINDS = frozenset()

# Αυτόματες ειδοποιήσεις μετά sync: μία φορά ανά ημέρα (είσοδος).
AUTO_NOTIFY_SEND_ONCE_KINDS = frozenset({"late_check_in"})


def notify_auto_send_once(notify_kind: str) -> bool:
    return (notify_kind or "").strip() in AUTO_NOTIFY_SEND_ONCE_KINDS


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


def _elapsed_same_date_minutes(from_min: int, to_min: int) -> int | None:
    elapsed = to_min - from_min
    return elapsed if elapsed >= 0 else None


def _schedule_end_minutes(row: dict[str, Any]) -> int | None:
    sched = row.get("schedule")
    if isinstance(sched, dict) and sched.get("hour_to"):
        parsed = _parse_clock_minutes(str(sched.get("hour_to")))
        if parsed is not None:
            return parsed
    label = str(row.get("schedule_label") or "").strip()
    if not label or label == "—" or re.search(r"ρεπο|ανάπαυση", label, re.I):
        return None
    parts = [p.strip() for p in label.split("·") if p.strip()]
    last = parts[-1] if parts else label
    match = re.search(r"[–\-]\s*(\d{1,2}:\d{2}(?::\d{2})?)", last)
    if match:
        return _parse_clock_minutes(match.group(1))
    return None


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


def _shift_calendar_iso(work_date_iso: str, days: int) -> str:
    from datetime import timedelta

    base = datetime.strptime(work_date_iso[:10], "%Y-%m-%d").date()
    return (base + timedelta(days=int(days))).strftime("%Y-%m-%d")


def expected_exit_spills_next_day(expected_exit: int) -> bool:
    """True όταν η αναμενόμενη έξοδος είναι μετά τα μεσάνυχτα (επόμενη ημέρα)."""
    return int(expected_exit) >= 24 * 60


def _allows_overnight_exit_on_date(row: dict[str, Any], *, today_iso: str) -> bool:
    """Έξοδος βάρδιας χθες που λήγει σήμερα (μετά τα μεσάνυχτα)."""
    hf = str(row.get("hour_from") or "").strip()
    ht = str(row.get("hour_to") or "").strip()
    if not hf or ht:
        return False
    wd_iso = ergani_date_to_iso(str(row.get("work_date") or ""))
    if not wd_iso or wd_iso == today_iso:
        return False
    expected = _expected_exit_minutes(row)
    if expected is None or not expected_exit_spills_next_day(expected):
        return False
    return _shift_calendar_iso(wd_iso, 1) == today_iso


def expected_exit_reference_date_iso(row: dict[str, Any]) -> str | None:
    """Ημερομηνία καταχώρησης εξόδου (ISO) — επόμενη μέρα αν η έξοδος περνά μεσάνυχτα."""
    wd_iso = ergani_date_to_iso(str(row.get("work_date") or ""))
    if not wd_iso:
        return None
    expected = _expected_exit_minutes(row)
    if expected is not None and expected_exit_spills_next_day(expected):
        return _shift_calendar_iso(wd_iso, 1)
    return wd_iso


def _schedule_duration_minutes(sched_start: int, sched_end: int) -> int | None:
    duration = _elapsed_work_day_minutes(sched_start, sched_end)
    return duration if duration > 0 else None


def _expected_exit_minutes(row: dict[str, Any]) -> int | None:
    """Αναμενόμενη έξοδος = ώρα εισόδου (κάρτα/πραγματική) + διάρκεια ψηφ. ωραρίου."""
    entry_min = _parse_clock_minutes(str(row.get("hour_from") or "").strip())
    if entry_min is None:
        return None
    sched_start = _schedule_start_minutes(row)
    sched_end = _schedule_end_minutes(row)
    if sched_start is None or sched_end is None:
        return None
    duration = _schedule_duration_minutes(sched_start, sched_end)
    if duration is None:
        return None
    return entry_min + duration


def _minutes_after_expected_exit(
    *,
    expected_exit: int,
    entry_min: int,
    now_min: int,
    on_next_calendar_day: bool = False,
) -> int | None:
    """Λεπτά μετά την αναμενόμενη έξοδο (υποστήριξη λήξης μετά τα μεσάνυχτα)."""
    if on_next_calendar_day:
        now_abs = now_min + 24 * 60
    elif expected_exit_spills_next_day(expected_exit) and now_min < entry_min:
        now_abs = now_min + 24 * 60
    else:
        now_abs = now_min
    elapsed = now_abs - expected_exit
    return elapsed if elapsed >= 0 else None


def _format_minutes_as_clock(total_min: int) -> str:
    wrapped = total_min % (24 * 60)
    h, m = divmod(wrapped, 60)
    return f"{h:02d}:{m:02d}"


def expected_exit_time_for_row(row: dict[str, Any]) -> str | None:
    mins = _expected_exit_minutes(row)
    if mins is None:
        return None
    return _format_minutes_as_clock(mins)


def expected_exit_from_schedule_and_entry(
    *,
    hour_from: str | None,
    schedule_hour_from: str | None,
    schedule_hour_to: str | None,
) -> str | None:
    return expected_exit_time_for_row(
        {
            "hour_from": hour_from,
            "schedule": {
                "hour_from": schedule_hour_from,
                "hour_to": schedule_hour_to,
            },
        }
    )


def resolve_today_notify_kind(
    row: dict[str, Any],
    *,
    now: datetime | None = None,
) -> str | None:
    """Επιστρέφει notify_kind ή None."""
    dt = now or datetime.now(tz_athens())
    wd_iso = ergani_date_to_iso(str(row.get("work_date") or ""))
    today_iso = _today_iso(dt)
    overnight_exit_today = _allows_overnight_exit_on_date(row, today_iso=today_iso)
    if not wd_iso or (wd_iso != today_iso and not overnight_exit_today):
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
    if not hf and sched_start is not None and wd_iso == today_iso:
        elapsed = _elapsed_same_date_minutes(sched_start, now_min)
        if elapsed is not None and elapsed >= NOTIFY_GRACE_MINUTES:
            return "late_check_in"

    if hf and not ht:
        entry_min = _parse_clock_minutes(hf)
        sched_start = _schedule_start_minutes(row)
        sched_end = _schedule_end_minutes(row)
        if entry_min is not None and sched_start is not None and sched_end is not None:
            duration = _schedule_duration_minutes(sched_start, sched_end)
            if duration is not None:
                expected_exit = entry_min + duration
                elapsed = _minutes_after_expected_exit(
                    expected_exit=expected_exit,
                    entry_min=entry_min,
                    now_min=now_min,
                    on_next_calendar_day=overnight_exit_today,
                )
                if elapsed is not None and elapsed >= NOTIFY_GRACE_MINUTES:
                    return "late_check_out"
                return None
        start_min = _parse_clock_minutes(hf)
        elapsed = (
            _elapsed_same_date_minutes(start_min, now_min)
            if start_min is not None
            else None
        )
        if elapsed is not None and elapsed >= 8 * 60:
            return "missing_exit_8h"

    return None


def card_action_for_today_kind(
    kind: str,
    *,
    schedule_hour_from: str | None = None,
    schedule_hour_to: str | None = None,
    hour_from: str | None = None,
) -> dict[str, str]:
    k = (kind or "").strip()
    if k in ("exit_without_entry", "late_check_in"):
        rt = (schedule_hour_from or "").strip()
        return {"card_event": "check_in", "retro_time": rt}
    if k in ("missing_exit_8h", "late_check_out"):
        rt = ""
        if k == "late_check_out":
            rt = expected_exit_from_schedule_and_entry(
                hour_from=hour_from,
                schedule_hour_from=schedule_hour_from,
                schedule_hour_to=schedule_hour_to,
            ) or (schedule_hour_to or "").strip()
        return {"card_event": "check_out", "retro_time": rt}
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
