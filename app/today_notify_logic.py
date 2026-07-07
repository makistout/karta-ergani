"""Κανόνες ειδοποίησης τύπου 2 — τρέχουσα ημέρα.

Κανόνες καμπάνας (resolve_today_notify_kind)
-------------------------------------------
Grace: 15 λεπτά (NOTIFY_GRACE_MINUTES) για είσοδο και έξοδο.

1. exit_without_entry — υπάρχει έξοδος (κάρτα/πραγματική) χωρίς είσοδο.

2. late_check_in — σήμερα, ενεργός, ψηφ. ωράριο εργασίας, χωρίς είσοδο,
   πέρασαν ≥15' από την έναρξη του ωραρίου. Αυτόματη αποστολή: μία φορά/ημέρα.

3. late_check_out — σήμερα (ή έξοδος βάρδιας χθες που λήγει σήμερα),
   υπάρχει είσοδος, όχι έξοδος, υπάρχει ψηφ. ωράριο εργασίας με ώρες:
   αναμενόμενη έξοδος = είσοδος + (τέλος_ωραρίου − αρχή_ωραρίου).
   Alert αν πέρασαν ≥15' από την αναμενόμενη έξοδο (συμπ. μετά τα μεσάνυχτα).

4. exit_needs_correction — έξοδος πριν από την είσοδο (λάθος χτύπημα).
   Αναμενόμενη έξοδος = είσοδος + (τέλος_ωραρίου − αρχή_ωραρίου) — όπως
   στο late_check_out. Alert αν πέρασαν ≥15' από την αναμενόμενη έξοδο.

5. missing_exit_8h — μόνο όταν ΔΕΝ υπάρχει ψηφ. ωράριο εργασίας σήμερα
   (ρεπό, «—», χωρίς ώρες): είσοδος χωρίς έξοδο και πέρασαν ≥8 ώρες.

Ακύρωση: card_event_blocks_today_notify — δεν στέλνει αν υπάρχει αντίστοιχο
χτύπημα κάρτας στη βάση erganiOS.

Ώρες εισόδου/εξόδου: merge_notify_work_hours — κάρτα υπερισχύει πραγματικής.

Άλλες ενέργειες (card_report / WTODaily, όχι καμπάνα sync):
rest_day, no_schedule, early_card, rest_with_card, no_schedule_work — βλ. card_report.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from app.work_card_payload import tz_athens

NOTIFY_GRACE_MINUTES = 15
NOTIFY_GRACE_CHECKOUT_MINUTES = NOTIFY_GRACE_MINUTES

TODAY_NOTIFY_KINDS = frozenset(
    {
        "exit_without_entry",
        "late_check_in",
        "late_check_out",
        "exit_needs_correction",
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
    "late_check_in": "καθυστέρηση εισόδου (>15' από ωράριο)",
    "late_check_out": "έλλειψη εξόδου (>15' από είσοδο+διάρκεια ωραρίου)",
    "exit_needs_correction": "χρειάζεται διόρθωση χτυπήματος εξόδου",
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
    return notify_kind_base(notify_kind) in AUTO_NOTIFY_SEND_ONCE_KINDS


def notify_kind_base(notify_kind: str | None) -> str:
    return str(notify_kind or "").strip().split("@", 1)[0]


def notify_kind_slot_start(notify_kind: str | None) -> str | None:
    parts = str(notify_kind or "").strip().split("@", 1)
    return parts[1] if len(parts) == 2 and parts[1] else None


def notify_kind_for_slot(base_kind: str, start_hm: str | None, *, include_slot: bool = True) -> str:
    start = _hm_short(start_hm)
    return f"{base_kind}@{start}" if include_slot and start else base_kind


def notify_kind_label(notify_kind: str | None) -> str:
    base = notify_kind_base(notify_kind)
    label = KIND_LABELS.get(base, base)
    slot = notify_kind_slot_start(notify_kind)
    return f"{label} ({slot})" if slot else label


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


def _schedule_intervals(row: dict[str, Any]) -> list[dict[str, Any]]:
    sched = row.get("schedule")
    if not isinstance(sched, dict):
        slots = row.get("schedule_slots")
        sched = {"intervals": slots} if isinstance(slots, list) else None
    if not isinstance(sched, dict):
        return []
    raw = sched.get("intervals")
    out: list[dict[str, Any]] = []
    if isinstance(raw, list):
        for item in raw:
            if not isinstance(item, dict):
                continue
            hf = _hm_short(str(item.get("hour_from") or ""))
            ht = _hm_short(str(item.get("hour_to") or ""))
            if hf and ht:
                start = _parse_clock_minutes(hf)
                end = _parse_clock_minutes(ht)
                if start is not None and end is not None:
                    out.append({"hour_from": hf, "hour_to": ht, "start": start, "end": end})
    if out:
        return out
    hf = _hm_short(str(sched.get("hour_from") or ""))
    ht = _hm_short(str(sched.get("hour_to") or ""))
    start = _parse_clock_minutes(hf)
    end = _parse_clock_minutes(ht)
    if hf and ht and start is not None and end is not None:
        return [{"hour_from": hf, "hour_to": ht, "start": start, "end": end}]
    return []


def _work_intervals(row: dict[str, Any]) -> list[dict[str, Any]]:
    raw = row.get("work_intervals")
    out: list[dict[str, Any]] = []
    if isinstance(raw, list):
        for item in raw:
            if not isinstance(item, dict):
                continue
            hf = _hm_short(str(item.get("hour_from") or ""))
            ht = _hm_short(str(item.get("hour_to") or ""))
            if hf or ht:
                out.append({"hour_from": hf, "hour_to": ht})
    if out:
        return out
    hf = _hm_short(str(row.get("hour_from") or ""))
    ht = _hm_short(str(row.get("hour_to") or ""))
    return [{"hour_from": hf, "hour_to": ht}] if hf or ht else []


def _work_entry_covers_interval(work: dict[str, Any], interval: dict[str, Any]) -> bool:
    entry = _parse_clock_minutes(str(work.get("hour_from") or ""))
    if entry is None:
        return False
    start = int(interval["start"])
    end = int(interval["end"])
    if end <= start:
        end += 24 * 60
    entry_abs = entry + (24 * 60 if entry < start and end > 24 * 60 else 0)
    return start <= entry_abs < end


def _completed_work_before_interval(work: dict[str, Any], interval: dict[str, Any]) -> bool:
    out_min = _parse_clock_minutes(str(work.get("hour_to") or ""))
    if out_min is None:
        return False
    return out_min <= int(interval["start"])


def schedule_interval_for_notify_kind(
    row: dict[str, Any],
    notify_kind: str | None,
) -> dict[str, Any] | None:
    slot = notify_kind_slot_start(notify_kind)
    intervals = _schedule_intervals(row)
    if slot:
        for interval in intervals:
            if interval.get("hour_from") == slot:
                return interval
    return intervals[0] if intervals else None


def _hm_short(value: str | None) -> str:
    m = re.match(r"^(\d{1,2}):(\d{2})", str(value or "").strip())
    if not m:
        return ""
    return f"{int(m.group(1)):02d}:{m.group(2)}"


def merge_notify_work_hours(
    *,
    hour_from: str | None,
    hour_to: str | None,
    card: dict[str, Any] | None = None,
) -> tuple[str | None, str | None]:
    """Συνδυάζει πραγματική + κάρτα· η κάρτα υπερισχύει όταν υπάρχει χτύπημα."""
    hf = str(hour_from or "").strip()
    ht = str(hour_to or "").strip()
    card_block = card if isinstance(card, dict) else {}
    card_in = _hm_short(str(card_block.get("check_in") or ""))
    card_out = _hm_short(str(card_block.get("check_out") or ""))
    if card_in:
        hf = card_in
    if card_out:
        ht = card_out
    return hf or None, ht or None


def notify_row_from_sources(
    *,
    work_date: Any,
    employee_active: Any = True,
    hour_from: str | None = None,
    hour_to: str | None = None,
    schedule: dict[str, Any] | None = None,
    schedule_label: str | None = None,
    card: dict[str, Any] | None = None,
    work_intervals: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    hf, ht = merge_notify_work_hours(
        hour_from=hour_from,
        hour_to=hour_to,
        card=card,
    )
    return {
        "work_date": work_date,
        "employee_active": employee_active,
        "hour_from": hf,
        "hour_to": ht,
        "work_intervals": work_intervals or [],
        "schedule": schedule,
        "schedule_label": schedule_label,
    }


def card_event_blocks_today_notify(
    employee_afm: str,
    work_date: str,
    kind: str,
) -> bool:
    """True όταν υπάρχει χτύπημα κάρτας που ακυρώνει την ειδοποίηση."""
    from app.repo_card import card_event_exists

    ref = ergani_date_to_iso(work_date)
    if not ref or not str(employee_afm or "").strip():
        return False
    k = notify_kind_base(kind)
    slot = notify_kind_slot_start(kind)
    if slot and k in ("late_check_in", "late_check_out"):
        from app.db import cursor

        f_type = "0" if k == "late_check_in" else "1"
        with cursor(commit=False) as cur:
            cur.execute(
                """
                SELECT TOP (1) 1
                FROM dbo.karta_card_event e
                INNER JOIN dbo.karta_declaration d ON d.id = e.declaration_id
                WHERE e.f_afm = ? AND e.f_reference_date = ? AND e.f_type = ?
                  AND d.success = 1
                  AND CONVERT(time, e.f_date) >= CONVERT(time, ?)
                """,
                (employee_afm.strip(), ref, f_type, slot),
            )
            return cur.fetchone() is not None
    if k == "late_check_in" and card_event_exists(employee_afm, ref, "0"):
        return True
    if k in ("late_check_out", "missing_exit_8h") and card_event_exists(employee_afm, ref, "1"):
        return True
    if k == "exit_without_entry" and card_event_exists(employee_afm, ref, "0"):
        return True
    return False


def notify_db_snapshot(
    *,
    employer_afm: str,
    branch_aa: str,
    employee_afm: str,
    work_date: str,
) -> dict[str, Any]:
    """Κατάσταση βάσης (πραγματική + κάρτα) τη στιγμή της ειδοποίησης."""
    from app.db import cursor
    from app.repo_card import card_event_exists
    from app.repo_work_log import _card_db_details_by_employee_work_date
    from app.work_card_payload import norm_afm

    wd = str(work_date or "").strip()[:32]
    ref_iso = ergani_date_to_iso(wd)
    e_afm = norm_afm(employee_afm)
    wl_hf = wl_ht = None
    wl_synced_at: str | None = None
    with cursor(commit=False) as cur:
        cur.execute(
            """
            SELECT hour_from, hour_to, CAST(synced_at AS datetime2)
            FROM dbo.karta_work_log
            WHERE employee_afm = ? AND work_date = ?
            """,
            (e_afm, wd),
        )
        row = cur.fetchone()
        if row:
            wl_hf = str(row[0] or "").strip() or None
            wl_ht = str(row[1] or "").strip() or None
            if row[2] is not None:
                wl_synced_at = str(row[2])[:19]

    card_in = card_out = None
    if wd:
        details = _card_db_details_by_employee_work_date(
            employer_afm,
            branch_aa,
            [wd],
        )
        slot = details.get((e_afm, wd), {})
        ci = slot.get("check_in") if isinstance(slot.get("check_in"), dict) else None
        co = slot.get("check_out") if isinstance(slot.get("check_out"), dict) else None
        if ci:
            card_in = str(ci.get("time") or "").strip() or None
        if co:
            card_out = str(co.get("time") or "").strip() or None

    return {
        "work_log_hour_from": wl_hf,
        "work_log_hour_to": wl_ht,
        "work_log_synced_at": wl_synced_at,
        "card_check_in": card_in,
        "card_check_out": card_out,
        "card_has_check_in": bool(ref_iso and card_event_exists(e_afm, ref_iso, "0")),
        "card_has_check_out": bool(ref_iso and card_event_exists(e_afm, ref_iso, "1")),
        "work_date_ergani": wd,
        "reference_date_iso": ref_iso or None,
    }


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


def _has_digital_work_schedule(row: dict[str, Any]) -> bool:
    """True όταν υπάρχει ψηφ. ωράριο εργασίας σήμερα (όχι ρεπό/κενό)."""
    sched = row.get("schedule")
    if isinstance(sched, dict):
        shift = str(sched.get("shift_type") or "").strip()
        if shift and re.search(r"ρεπο|ανάπαυση", shift, re.I):
            return False
    label = str(row.get("schedule_label") or "").strip()
    if label and label != "—" and re.search(r"ρεπο|ανάπαυση", label, re.I):
        return False
    return (
        _schedule_start_minutes(row) is not None
        and _schedule_end_minutes(row) is not None
    )


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


def _has_exit_before_entry_anomaly(row: dict[str, Any]) -> bool:
    entry_min = _parse_clock_minutes(str(row.get("hour_from") or "").strip())
    exit_min = _parse_clock_minutes(str(row.get("hour_to") or "").strip())
    if entry_min is None or exit_min is None:
        return False
    return _elapsed_same_date_minutes(entry_min, exit_min) is None


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


def _format_duration_greek(total_minutes: int) -> str:
    hours, minutes = divmod(int(total_minutes), 60)
    if hours and minutes:
        return f"{hours} ώρ{'α' if hours == 1 else 'ες'} {minutes} λεπτά"
    if hours:
        return f"{hours} ώρ{'α' if hours == 1 else 'ες'}"
    return f"{minutes} λεπτά"


def format_digital_schedule_summary(
    schedule_hour_from: str | None,
    schedule_hour_to: str | None,
) -> str | None:
    """Μία γραμμή με ώρες εργασίας από ψηφιακό ωράριο για ειδοποίηση."""
    hf = str(schedule_hour_from or "").strip()
    ht = str(schedule_hour_to or "").strip()
    if not hf or not ht:
        return None
    start = _parse_clock_minutes(hf)
    end = _parse_clock_minutes(ht)
    if start is None or end is None:
        return f"Ώρες εργασίας (ψηφ. ωράριο): {hf} – {ht}"
    duration = _schedule_duration_minutes(start, end)
    if duration is None:
        return f"Ώρες εργασίας (ψηφ. ωράριο): {hf} – {ht}"
    return (
        f"Ώρες εργασίας (ψηφ. ωράριο): {hf} – {ht} "
        f"({_format_duration_greek(duration)})"
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

    intervals = _schedule_intervals(row)
    work_intervals = _work_intervals(row)
    if intervals and wd_iso == today_iso:
        open_work = next((w for w in work_intervals if w.get("hour_from") and not w.get("hour_to")), None)
        if open_work:
            entry_min = _parse_clock_minutes(open_work.get("hour_from"))
            interval = next((i for i in intervals if _work_entry_covers_interval(open_work, i)), None)
            if interval and entry_min is not None:
                expected_exit = entry_min + (_schedule_duration_minutes(int(interval["start"]), int(interval["end"])) or 0)
                elapsed = _minutes_after_expected_exit(
                    expected_exit=expected_exit,
                    entry_min=entry_min,
                    now_min=now_min,
                )
                if elapsed is not None and elapsed >= NOTIFY_GRACE_CHECKOUT_MINUTES:
                    return notify_kind_for_slot(
                        "late_check_out",
                        interval.get("hour_from"),
                        include_slot=len(intervals) > 1,
                    )
                return None
        due: list[dict[str, Any]] = []
        for interval in intervals:
            elapsed = _elapsed_same_date_minutes(int(interval["start"]), now_min)
            if elapsed is None or elapsed < NOTIFY_GRACE_MINUTES:
                continue
            if any(_work_entry_covers_interval(w, interval) for w in work_intervals):
                continue
            due.append(interval)
        if due:
            interval = due[-1]
            return notify_kind_for_slot(
                "late_check_in",
                interval.get("hour_from"),
                include_slot=len(intervals) > 1,
            )

    sched_start = _schedule_start_minutes(row)
    if not hf and sched_start is not None and wd_iso == today_iso:
        elapsed = _elapsed_same_date_minutes(sched_start, now_min)
        if elapsed is not None and elapsed >= NOTIFY_GRACE_MINUTES:
            return notify_kind_for_slot(
                "late_check_in",
                _hm_short(str(row.get("schedule", {}).get("hour_from") if isinstance(row.get("schedule"), dict) else "")),
                include_slot=False,
            )

    exit_before_entry = bool(hf and ht and _has_exit_before_entry_anomaly(row))
    if hf and (not ht or exit_before_entry):
        entry_min = _parse_clock_minutes(hf)
        if entry_min is None:
            return None
        if _has_digital_work_schedule(row):
            expected_exit = _expected_exit_minutes(row)
            if expected_exit is not None:
                elapsed = _minutes_after_expected_exit(
                    expected_exit=expected_exit,
                    entry_min=entry_min,
                    now_min=now_min,
                    on_next_calendar_day=overnight_exit_today,
                )
                if elapsed is not None and elapsed >= NOTIFY_GRACE_CHECKOUT_MINUTES:
                    if exit_before_entry:
                        return "exit_needs_correction"
                    return notify_kind_for_slot(
                        "late_check_out",
                        _hm_short(str((row.get("schedule") or {}).get("hour_from") if isinstance(row.get("schedule"), dict) else "")),
                        include_slot=False,
                    )
            return None
        if not ht:
            elapsed = _elapsed_same_date_minutes(entry_min, now_min)
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
    k = notify_kind_base(kind)
    if k in ("exit_without_entry", "late_check_in"):
        rt = notify_kind_slot_start(kind) or (schedule_hour_from or "").strip()
        return {"card_event": "check_in", "retro_time": rt}
    if k in ("missing_exit_8h", "late_check_out", "exit_needs_correction"):
        rt = ""
        if k in ("late_check_out", "exit_needs_correction"):
            rt = expected_exit_from_schedule_and_entry(
                hour_from=hour_from,
                schedule_hour_from=schedule_hour_from,
                schedule_hour_to=schedule_hour_to,
            ) or (schedule_hour_to or "").strip()
        return {"card_event": "check_out", "retro_time": rt}
    return {"card_event": "check_in", "retro_time": ""}


def today_wto_daily_eligible(notify_kind: str) -> bool:
    return notify_kind_base(notify_kind) in WTO_DAILY_NOTIFY_KINDS


def today_leave_eligible(
    notify_kind: str,
    *,
    schedule_hour_from: str | None = None,
    hour_from: str | None = None,
    hour_to: str | None = None,
) -> bool:
    """Άδεια μόνο πριν την έναρξη ψηφ. ωραρίου — όχι μετά (ούτε σε late_check_in alert)."""
    del schedule_hour_from, hour_from, hour_to
    return False
