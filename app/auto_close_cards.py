"""Αυτόματο κλείσιμο ανοιχτών καρτών της τελευταίας ημέρας εργασίας."""

from __future__ import annotations

import random
import time
from datetime import datetime, timedelta
from typing import Any

from app.audit_log import record_audit_event
from app.date_util import format_date_for_ergani
from app.ergani_env import api_login_credentials, client_for_store, store_api_context
from app.http_helpers import json_or_text, response_body_text
from app.karta_log import KartaLogger
from app.repo_card import card_event_exists, persist_wrk_card_submit
from app.repo_work_log import (
    enrich_work_log_rows_with_schedule,
    list_work_log_for_store,
)
from app.work_card_payload import (
    RETRO_AITIOLOGIA_INTERNET,
    SUBMISSION_CODE_WRK_CARD,
    WorkCardPayloadError,
    build_wrk_card_se_payload,
    ergani_forbids_aitiologia,
    norm_afm,
    tz_athens,
)
from app.punch_time_jitter import apply_punch_time_jitter
from app.work_card_guards import (
    OVERNIGHT_EXIT_BEFORE_MINUTES,
    has_entry_for_checkout,
)
from config import Config

OPERATION_AUTO_CLOSE_PREV_DAY = "auto_close_prev_day_cards"
DEFAULT_REST_DURATION_MINUTES = 8 * 60
# Ώρες 00:00–11:59 = μετά τα μεσάνυχτα (κλείνει προηγούμενη, με * αν χρειάζεται).
# Ώρες 12:00–23:59 = πριν τα μεσάνυχτα (κλείνει τρέχουσα, χωρίς *).
_AUTO_CLOSE_AFTER_MIDNIGHT_HOUR_LT = 12
# Εκτέλεση μόνο μέσα σε αυτό το παράθυρο μετά την ώρα ρύθμισης
# (όχι «οποτεδήποτε μετά», π.χ. 02:00 στις 20:45).
_AUTO_CLOSE_RUN_WINDOW_MINUTES = 15


def normalize_auto_close_time(value: str | None) -> str:
    raw = str(value or "").strip().replace(".", ":")
    try:
        hh, mm = raw.split(":", 1)
        h = int(hh)
        m = int(mm)
    except (TypeError, ValueError):
        return "00:30"
    if h < 0 or h > 23 or m < 0 or m > 59:
        return "00:30"
    return f"{h:02d}:{m:02d}"


def normalize_optional_auto_close_time(value: str | None) -> str | None:
    """Προαιρετική ώρα κλεισίματος. Κενό → None (βάσει ωραρίου). Δέχεται 23:00 ή 23.00."""
    raw = str(value or "").strip().replace(".", ":")
    if not raw:
        return None
    try:
        hh, mm = raw.split(":", 1)
        h = int(hh)
        m = int(mm)
    except (TypeError, ValueError):
        return None
    if h < 0 or h > 23 or m < 0 or m > 59:
        return None
    return f"{h:02d}:{m:02d}"


_FIXED_EXIT_WINDOW_MINUTES = 30


def _random_offsets_in_window(
    count: int,
    *,
    window: int = _FIXED_EXIT_WINDOW_MINUTES,
    rng: random.Random | None = None,
) -> list[int]:
    """Τυχαία λεπτά offset μέσα στο [0, window) — μοναδικά όταν count ≤ window."""
    if count <= 0:
        return []
    r = rng or random.Random()
    if count <= window:
        return sorted(r.sample(range(window), count))
    return sorted(r.randrange(window) for _ in range(count))


def _natural_exit_abs_minutes(item: dict[str, Any]) -> int | None:
    """Απόλυτα λεπτά φυσικής εξόδου από είσοδο + διάρκεια (μπορεί ≥ 24h)."""
    entry = _parse_clock_minutes(str(item.get("hour_from") or ""))
    try:
        duration = int(item.get("duration_minutes"))
    except (TypeError, ValueError):
        duration = None
    if entry is not None and duration is not None and duration > 0:
        return entry + duration
    exit_min = _parse_clock_minutes(str(item.get("retro_time") or ""))
    if exit_min is None:
        return None
    work = str(item.get("work_date_iso") or item.get("reference_date") or "").strip()
    event = str(item.get("event_date_iso") or work).strip()
    if work and event and event != work:
        return exit_min + 24 * 60
    # Αν η έξοδος ρολογιού είναι πριν την είσοδο την ίδια μέρα, μετράει ως overnight.
    if entry is not None and exit_min < entry:
        return exit_min + 24 * 60
    return exit_min


def _apply_fixed_exit_window(
    plan: list[dict[str, Any]],
    *,
    fixed_hm: str,
    allow_overnight_star: bool,
    rng: random.Random | None = None,
) -> None:
    """Για check_out: αν η φυσική έξοδος είναι πριν την ώρα κλεισίματος, μένει.
    Αλλιώς μπαίνει τυχαία στο [fixed_hm, +30′).
    """
    base = _clock_hm_to_minutes(fixed_hm)
    candidates: list[dict[str, Any]] = []
    for item in plan:
        if item.get("event") != "check_out":
            continue
        natural = _natural_exit_abs_minutes(item)
        if natural is not None and natural < base:
            # Κλείνει ήδη πριν την αναγραφόμενη ώρα → κράτα ωράριο.
            continue
        candidates.append(item)
    if not candidates:
        return
    offsets = _random_offsets_in_window(len(candidates), rng=rng)
    for item, off in zip(candidates, offsets):
        exit_abs = base + int(off)
        work_date_iso = str(item.get("work_date_iso") or item.get("reference_date") or "")
        reference_date = work_date_iso
        event_date_iso = work_date_iso
        if exit_abs >= 24 * 60:
            if allow_overnight_star:
                exit_abs -= 24 * 60
                nxt = _iso_shift(work_date_iso, 1)
                if nxt:
                    event_date_iso = nxt
            else:
                exit_abs = min(exit_abs, 24 * 60 - 1)
        entry_min = _parse_clock_minutes(str(item.get("hour_from") or ""))
        duration = (
            (exit_abs + (24 * 60 if event_date_iso != reference_date else 0) - entry_min) % (24 * 60)
            if entry_min is not None
            else int(item.get("duration_minutes") or 0)
        )
        item["retro_time"] = _format_minutes_as_clock(exit_abs)
        item["reference_date"] = reference_date
        item["event_date_iso"] = event_date_iso
        item["duration_minutes"] = duration
        item["duration_source"] = "fixed_window"


def auto_close_allows_overnight_star(cfg: dict[str, Any]) -> bool:
    """True όταν η ώρα εκτέλεσης είναι μετά τα μεσάνυχτα (00:00–11:59)."""
    run_time = normalize_auto_close_time(str(cfg.get("auto_close_prev_day_time") or "00:30"))
    return int(run_time.split(":", 1)[0]) < _AUTO_CLOSE_AFTER_MIDNIGHT_HOUR_LT


def resolve_auto_close_target(
    cfg: dict[str, Any],
    *,
    now: datetime | None = None,
) -> tuple[str, bool]:
    """Επιστρέφει (work_date_iso, allow_overnight_star).

    - Ώρα εκτέλεσης πριν τα μεσάνυχτα (12:00–23:59): τρέχουσα ημερολογιακή μέρα, χωρίς *.
    - Ώρα εκτέλεσης μετά τα μεσάνυχτα (00:00–11:59): προηγούμενη μέρα, με * αν η έξοδος περνάει μεσάνυχτα.
    """
    local_now = (now or datetime.now(tz_athens())).astimezone(tz_athens())
    allow_overnight = auto_close_allows_overnight_star(cfg)
    today = local_now.date()
    if allow_overnight:
        return (today - timedelta(days=1)).isoformat(), True
    return today.isoformat(), False


def _clock_hm_to_minutes(value: str) -> int:
    hh, mm = str(value).split(":", 1)
    return int(hh) * 60 + int(mm)


def should_run_auto_close_prev_day(
    cfg: dict[str, Any],
    *,
    now: datetime | None = None,
) -> tuple[bool, str, str]:
    """Επιστρέφει (τρέχει, work_date ISO προς κλείσιμο, λόγος)."""
    if not bool(cfg.get("auto_close_prev_day_enabled")):
        return False, "", "ρύθμιση ανενεργή"
    local_now = (now or datetime.now(tz_athens())).astimezone(tz_athens())
    work_date, _allow_overnight = resolve_auto_close_target(cfg, now=local_now)
    if str(cfg.get("auto_close_prev_day_last_run_date") or "").strip() == work_date:
        return False, work_date, "έχει ήδη εκτελεστεί για αυτή την ημέρα εργασίας"
    run_time = normalize_auto_close_time(str(cfg.get("auto_close_prev_day_time") or "00:30"))
    now_hm = local_now.strftime("%H:%M")
    if now_hm < run_time:
        return False, work_date, f"αναμονή μέχρι {run_time}"
    elapsed = _clock_hm_to_minutes(now_hm) - _clock_hm_to_minutes(run_time)
    if elapsed > _AUTO_CLOSE_RUN_WINDOW_MINUTES:
        return (
            False,
            work_date,
            f"εκτός παραθύρου εκτέλεσης {run_time} (+{_AUTO_CLOSE_RUN_WINDOW_MINUTES}')",
        )
    return True, work_date, "έτοιμο"


def _parse_clock_minutes(value: str | None) -> int | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    parts = raw.split(":")
    if len(parts) < 2:
        return None
    try:
        h = int(parts[0])
        m = int(parts[1])
    except ValueError:
        return None
    if h < 0 or h > 23 or m < 0 or m > 59:
        return None
    return h * 60 + m


def _format_minutes_as_clock(total_minutes: int) -> str:
    wrapped = int(total_minutes) % (24 * 60)
    h, m = divmod(wrapped, 60)
    return f"{h:02d}:{m:02d}"


def _auto_close_queue_delay_seconds() -> int:
    low = max(0, int(Config.KARTA_AUTO_CLOSE_QUEUE_MIN_DELAY_SECONDS or 0))
    high = max(low, int(Config.KARTA_AUTO_CLOSE_QUEUE_MAX_DELAY_SECONDS or low))
    if high <= 0:
        return 0
    if high == low:
        return low
    return random.randint(low, high)


def _duration_between(start: int | None, end: int | None) -> int | None:
    if start is None or end is None:
        return None
    duration = end - start
    if duration < 0:
        duration += 24 * 60
    return duration if duration > 0 else None


def _schedule_duration_minutes(row: dict[str, Any]) -> int | None:
    durations: list[int] = []
    slots = row.get("schedule_slots")
    if isinstance(slots, list):
        for slot in slots:
            if not isinstance(slot, dict):
                continue
            dur = _duration_between(
                _parse_clock_minutes(slot.get("hour_from")),
                _parse_clock_minutes(slot.get("hour_to")),
            )
            if dur:
                durations.append(dur)
    if not durations:
        sched = row.get("schedule")
        if isinstance(sched, dict):
            dur = _duration_between(
                _parse_clock_minutes(sched.get("hour_from")),
                _parse_clock_minutes(sched.get("hour_to")),
            )
            if dur:
                durations.append(dur)
    return sum(durations) if durations else None


def _row_is_active(row: dict[str, Any]) -> bool:
    v = row.get("employee_active")
    return not (v is False or v == 0 or v == "0")


def _portal_open_entry(row: dict[str, Any]) -> tuple[str, str]:
    """Ώρες από portal πραγματική (όχι από δήλωση κάρτας / fallback)."""
    hour_from = str(
        row.get("portal_hour_from")
        if row.get("portal_hour_from") is not None
        else row.get("hour_from")
        or ""
    ).strip()
    hour_to = str(
        row.get("portal_hour_to")
        if row.get("portal_hour_to") is not None
        else row.get("hour_to")
        or ""
    ).strip()
    return hour_from, hour_to


def _is_card_fallback_row(row: dict[str, Any]) -> bool:
    if row.get("from_card_event_fallback"):
        return True
    if str(row.get("source_aa") or "").strip() == "card_event_fallback":
        return True
    src_from = str(row.get("hour_from_source") or "").strip().lower()
    src_to = str(row.get("hour_to_source") or "").strip().lower()
    if src_from.startswith("card_event") or src_to.startswith("card_event"):
        return True
    if row.get("id") is None and (
        row.get("from_card_event_fallback") is True
        or str(row.get("source_aa") or "").strip() == "card_event_fallback"
    ):
        return True
    return False


def _has_portal_work_log_entry(row: dict[str, Any], hour_from: str) -> bool:
    """Αυτόματη έξοδος μόνο με πραγματική είσοδο από karta_work_log."""
    if not hour_from:
        return False
    return not _is_card_fallback_row(row)


def _has_portal_work_log_exit(row: dict[str, Any], hour_to: str) -> bool:
    """Αυτόματη είσοδος μόνο με πραγματική έξοδο από karta_work_log."""
    if not hour_to:
        return False
    return not _is_card_fallback_row(row)


def _iso_shift(work_date_iso: str, days: int) -> str | None:
    try:
        d = datetime.strptime(str(work_date_iso).strip()[:10], "%Y-%m-%d").date()
    except ValueError:
        return None
    return (d + timedelta(days=days)).isoformat()


def _plan_item_base(
    row: dict[str, Any],
    *,
    afm: str,
    name: str,
    work_date_iso: str,
    reference_date: str,
    event_date_iso: str,
    retro_time: str,
    duration: int,
    event: str,
    hour_from: str,
    hour_to: str,
) -> dict[str, Any]:
    return {
        "employee_afm": afm,
        "employee_name": name,
        "employee_last_name": str(row.get("eponymo") or "").strip(),
        "employee_first_name": str(row.get("onoma") or "").strip(),
        "work_date_iso": work_date_iso,
        "reference_date": reference_date,
        "event_date_iso": event_date_iso,
        "retro_time": retro_time,
        "duration_minutes": duration,
        "duration_source": "schedule" if _schedule_duration_minutes(row) else "rest_8h",
        "event": event,
        "hour_from": hour_from,
        "hour_to": hour_to,
    }


def _build_previous_day_close_plan(
    rows: list[dict[str, Any]],
    *,
    allow_overnight_star: bool = True,
    next_day_open_entries: dict[str, int] | None = None,
    fixed_exit_hm: str | None = None,
    rng: random.Random | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    plan: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    fixed_hm = normalize_optional_auto_close_time(fixed_exit_hm)
    for row in rows:
        afm = str(row.get("employee_afm") or "").strip()
        name = f"{row.get('eponymo') or ''} {row.get('onoma') or ''}".strip() or afm
        hour_from, hour_to = _portal_open_entry(row)
        if not afm:
            continue
        work_date_iso = str(row.get("work_date_iso") or "").strip()
        if not work_date_iso:
            skipped.append({"employee_afm": afm, "employee_name": name, "reason": "άγνωστη ημερομηνία"})
            continue
        if not _row_is_active(row):
            skipped.append({"employee_afm": afm, "employee_name": name, "reason": "ανενεργός εργαζόμενος"})
            continue

        # Έξοδος χωρίς είσοδο → συμπλήρωση εισόδου.
        if hour_to and not hour_from:
            if not _has_portal_work_log_exit(row, hour_to):
                skipped.append({
                    "employee_afm": afm,
                    "employee_name": name,
                    "reason": "χωρίς πραγματική έξοδο",
                })
                continue
            exit_min = _parse_clock_minutes(hour_to)
            if exit_min is None:
                skipped.append({"employee_afm": afm, "employee_name": name, "reason": "μη έγκυρη ώρα εξόδου"})
                continue
            overnight_orphan = bool(row.get("overnight_exit_orphan"))
            # Exit-only στις πρώτες ώρες της ίδιας ημερολογιακής μέρας ανήκει στην προηγούμενη
            # μέρα εργασίας — το κλείνουμε όταν φορτώνουμε ως orphan από την επόμενη μέρα.
            if (
                allow_overnight_star
                and not overnight_orphan
                and exit_min < OVERNIGHT_EXIT_BEFORE_MINUTES
            ):
                continue
            duration = _schedule_duration_minutes(row) or DEFAULT_REST_DURATION_MINUTES
            if overnight_orphan:
                # Έξοδος μετά τα μεσάνυχτα (ημερολογιακά επόμενη) → είσοδος στην work_date.
                entry_abs = exit_min + 24 * 60 - duration
            else:
                entry_abs = exit_min - duration
            entry_abs = apply_punch_time_jitter(entry_abs)
            reference_date = work_date_iso
            event_date_iso = work_date_iso
            if entry_abs < 0:
                entry_abs += 24 * 60
                if allow_overnight_star:
                    prev = _iso_shift(work_date_iso, -1)
                    if prev:
                        reference_date = prev
                        event_date_iso = prev
            elif entry_abs >= 24 * 60:
                entry_abs -= 24 * 60
                nxt = _iso_shift(work_date_iso, 1)
                if nxt and allow_overnight_star:
                    event_date_iso = nxt
            if card_event_exists(afm, reference_date, "0"):
                skipped.append({
                    "employee_afm": afm,
                    "employee_name": name,
                    "reason": "υπάρχει ήδη είσοδος κάρτας",
                })
                continue
            plan.append(_plan_item_base(
                row,
                afm=afm,
                name=name,
                work_date_iso=work_date_iso,
                reference_date=reference_date,
                event_date_iso=event_date_iso,
                retro_time=_format_minutes_as_clock(entry_abs),
                duration=duration,
                event="check_in",
                hour_from="",
                hour_to=hour_to,
            ))
            continue

        # Είσοδος χωρίς έξοδο → συμπλήρωση εξόδου.
        if hour_from and hour_to:
            continue
        if not hour_from or not _has_portal_work_log_entry(row, hour_from):
            skipped.append({
                "employee_afm": afm,
                "employee_name": name,
                "reason": "χωρίς πραγματική είσοδο",
            })
            continue
        entry_min = _parse_clock_minutes(hour_from)
        if entry_min is None:
            skipped.append({"employee_afm": afm, "employee_name": name, "reason": "μη έγκυρη ώρα εισόδου"})
            continue

        # Αν υπάρχει ανοιχτή είσοδος στην επόμενη μέρα < 03:00 για τον ίδιο
        # εργαζόμενο, σημαίνει ότι χτύπησε «είσοδο» αντί «έξοδο» μετά τα
        # μεσάνυχτα.  Χρησιμοποιούμε εκείνη την ώρα ως έξοδο με *.
        # (Παραλείπεται όταν υπάρχει σταθερή ώρα κλεισίματος.)
        _nxt_entry = None if fixed_hm else (next_day_open_entries or {}).get(afm)
        if _nxt_entry is not None and allow_overnight_star:
            exit_abs = _nxt_entry  # ώρα στην επόμενη ημέρα (π.χ. 59 = 00:59)
            reference_date = work_date_iso
            nxt = _iso_shift(work_date_iso, 1)
            event_date_iso = nxt if nxt else work_date_iso
            duration = (exit_abs + 24 * 60 - entry_min) % (24 * 60) or DEFAULT_REST_DURATION_MINUTES
        else:
            duration = _schedule_duration_minutes(row) or DEFAULT_REST_DURATION_MINUTES
            exit_abs = apply_punch_time_jitter(entry_min + duration)
            # Μετά τα μεσάνυχτα: f_reference_date = μέρα εισόδου, f_date στην επόμενη αν περνάει 24:00 (*).
            # Πριν τα μεσάνυχτα: ίδια ημερολογιακή μέρα — χωρίς *.
            reference_date = work_date_iso
            event_date_iso = work_date_iso
            if allow_overnight_star and exit_abs >= 24 * 60:
                nxt = _iso_shift(work_date_iso, 1)
                if nxt:
                    event_date_iso = nxt
        if card_event_exists(afm, reference_date, "1") or (
            event_date_iso != reference_date
            and card_event_exists(afm, event_date_iso, "1")
        ):
            skipped.append({"employee_afm": afm, "employee_name": name, "reason": "υπάρχει ήδη έξοδος κάρτας"})
            continue
        plan.append(_plan_item_base(
            row,
            afm=afm,
            name=name,
            work_date_iso=work_date_iso,
            reference_date=reference_date,
            event_date_iso=event_date_iso,
            retro_time=_format_minutes_as_clock(exit_abs),
            duration=duration,
            event="check_out",
            hour_from=hour_from,
            hour_to="",
        ))
    if fixed_hm:
        _apply_fixed_exit_window(
            plan,
            fixed_hm=fixed_hm,
            allow_overnight_star=allow_overnight_star,
            rng=rng,
        )
    return plan, skipped


def _load_previous_day_rows(
    cfg: dict[str, Any],
    work_date_iso: str,
    *,
    include_next_day_overnight_exits: bool = False,
) -> list[dict[str, Any]]:
    ctx = store_api_context(cfg)
    work_date = format_date_for_ergani(work_date_iso)
    # Μόνο portal πραγματική — χωρίς fallback χτυπημάτων κάρτας που «εφευρίσκουν» είσοδο.
    rows = list_work_log_for_store(ctx["employer_afm"], ctx["branch_aa"], work_date, limit=5000)
    for row in rows:
        row["portal_hour_from"] = str(row.get("hour_from") or "").strip()
        row["portal_hour_to"] = str(row.get("hour_to") or "").strip()
        row["work_date_iso"] = work_date_iso
        row["overnight_exit_orphan"] = False
    enrich_dates = [work_date]

    # Εισόδους χωρίς έξοδο στην επόμενη μέρα (< 03:00): αν ο εργαζόμενος
    # χτύπησε «είσοδο» αντί «έξοδο» μετά τα μεσάνυχτα, η αυτόματη έξοδος
    # γίνεται εκείνη την ώρα με *.
    _next_day_open_entries: dict[str, int] = {}

    if include_next_day_overnight_exits:
        next_iso = _iso_shift(work_date_iso, 1)
        if next_iso:
            next_ergani = format_date_for_ergani(next_iso)
            next_rows = list_work_log_for_store(
                ctx["employer_afm"], ctx["branch_aa"], next_ergani, limit=5000
            )
            for row in next_rows:
                hour_from = str(row.get("hour_from") or "").strip()
                hour_to = str(row.get("hour_to") or "").strip()
                nxt_afm = str(row.get("employee_afm") or "").strip()
                # Exit-only orphan → append στα rows (υπάρχουσα λογική).
                if not hour_from and hour_to:
                    exit_min = _parse_clock_minutes(hour_to)
                    if exit_min is not None and exit_min < OVERNIGHT_EXIT_BEFORE_MINUTES:
                        row["portal_hour_from"] = ""
                        row["portal_hour_to"] = hour_to
                        row["work_date_iso"] = work_date_iso
                        row["work_date"] = work_date
                        row["overnight_exit_orphan"] = True
                        rows.append(row)
                    continue
                # Entry-only < 03:00 → αποθήκευση για χρήση ως exit
                if hour_from and not hour_to and nxt_afm:
                    entry_min = _parse_clock_minutes(hour_from)
                    if entry_min is not None and entry_min < OVERNIGHT_EXIT_BEFORE_MINUTES:
                        _next_day_open_entries[nxt_afm] = entry_min
            enrich_dates.append(next_ergani)

    enrich_work_log_rows_with_schedule(
        rows, ctx["employer_afm"], ctx["branch_aa"], enrich_dates
    )
    return rows, _next_day_open_entries


def format_auto_close_notification_text(
    *,
    store_name: str,
    work_date_iso: str,
    submitted: int,
    failed: int,
    skipped: int,
    plan_count: int,
) -> str:
    work_date = format_date_for_ergani(work_date_iso)
    status = "ολοκληρώθηκε" if failed == 0 else "ολοκληρώθηκε με αποτυχίες"
    return "\n".join([
        f"erganiOS — {store_name}",
        f"Το αυτόματο κλείσιμο ανοιχτών καρτών για {work_date} {status}.",
        f"Υποβολές εισόδου/εξόδου: {submitted}/{plan_count}",
        f"Αποτυχίες: {failed}",
        f"Εκτός/παράλειψη: {skipped}",
    ])


def _send_auto_close_notification(
    *,
    store_id: int,
    store_name: str,
    work_date_iso: str,
    submitted: int,
    failed: int,
    skipped_count: int,
    plan_count: int,
) -> dict[str, Any]:
    from app.email_notify import EmailNotConfigured, send_notification_email
    from app.repo_notify_recipients import (
        list_deliverable_recipients,
        list_email_deliverable_recipients,
    )
    from app.telegram_notify import TelegramNotConfigured, send_telegram_message

    text = format_auto_close_notification_text(
        store_name=store_name,
        work_date_iso=work_date_iso,
        submitted=submitted,
        failed=failed,
        skipped=skipped_count,
        plan_count=plan_count,
    )
    telegram_sent = 0
    email_sent = 0
    errors: list[str] = []

    try:
        telegram_recipients = list_deliverable_recipients(store_id)
    except Exception as ex:
        telegram_recipients = []
        errors.append(f"Telegram recipients: {ex}")
    try:
        email_recipients = list_email_deliverable_recipients(store_id)
    except Exception as ex:
        email_recipients = []
        errors.append(f"Email recipients: {ex}")

    for rec in telegram_recipients:
        chat_id = str(rec.get("telegram_chat_id") or "").strip()
        if not chat_id:
            continue
        try:
            send_telegram_message(chat_id, text)
            telegram_sent += 1
        except TelegramNotConfigured as ex:
            errors.append(f"Telegram: {ex}")
            break
        except Exception as ex:
            errors.append(f"Telegram {rec.get('name')}: {ex}")

    work_date = format_date_for_ergani(work_date_iso)
    for rec in email_recipients:
        email = str(rec.get("email") or "").strip()
        if not email:
            continue
        try:
            send_notification_email(
                email,
                "erganiOS — Αυτόματο κλείσιμο καρτών",
                title="Αυτόματο κλείσιμο καρτών",
                preheader=f"{store_name} · {work_date}",
                store_name=store_name,
                employee_name="—",
                employee_afm=None,
                work_date=work_date,
                problem="Ολοκληρώθηκε η αυτόματη ενέργεια κλεισίματος ανοιχτών καρτών της τελευταίας ημέρας.",
                details=[
                    ("Υποβολές εισόδου/εξόδου", f"{submitted}/{plan_count}"),
                    ("Αποτυχίες", str(failed)),
                    ("Εκτός/παράλειψη", str(skipped_count)),
                ],
                footer_note="Η ειδοποίηση αφορά αυτόματη ενέργεια του scheduled sync.",
            )
            email_sent += 1
        except EmailNotConfigured as ex:
            errors.append(f"Email: {ex}")
            break
        except Exception as ex:
            errors.append(f"Email {rec.get('name')}: {ex}")

    return {
        "telegram_sent": telegram_sent,
        "email_sent": email_sent,
        "sent": telegram_sent + email_sent,
        "errors": errors,
    }


def run_auto_close_prev_day_for_store(
    cfg: dict[str, Any],
    *,
    work_date_iso: str,
    parent_run_id: str | None = None,
) -> dict[str, Any]:
    sid = int(cfg["id"])
    ctx = store_api_context(cfg)
    log = KartaLogger(
        OPERATION_AUTO_CLOSE_PREV_DAY,
        store_id=sid,
        store_name=str(cfg.get("name") or sid),
        run_id=parent_run_id,
        extra={
            "work_date": work_date_iso,
            "employer_afm": ctx.get("employer_afm"),
            "branch_aa": ctx.get("branch_aa"),
        },
    )
    allow_overnight_star = auto_close_allows_overnight_star(cfg)
    rows, next_day_open_entries = _load_previous_day_rows(
        cfg,
        work_date_iso,
        include_next_day_overnight_exits=allow_overnight_star,
    )
    plan, skipped = _build_previous_day_close_plan(
        rows,
        allow_overnight_star=allow_overnight_star,
        next_day_open_entries=next_day_open_entries,
        fixed_exit_hm=cfg.get("auto_close_fixed_exit_time"),
    )
    if not plan:
        log.info(
            f"Αυτόματο κλείσιμο καρτών {work_date_iso}: δεν υπάρχουν ανοιχτές είσοδοι/έξοδοι",
            skipped=len(skipped),
            allow_overnight_star=allow_overnight_star,
        )
        notification = _send_auto_close_notification(
            store_id=sid,
            store_name=str(cfg.get("name") or sid),
            work_date_iso=work_date_iso,
            submitted=0,
            failed=0,
            skipped_count=len(skipped),
            plan_count=0,
        )
        return {
            "success": True,
            "work_date": work_date_iso,
            "submitted": 0,
            "failed": 0,
            "skipped": skipped,
            "notification": notification,
        }

    client = client_for_store(cfg)
    api_user, api_pwd, api_ut = api_login_credentials(cfg)
    auth_resp = client.authenticate(api_user, api_pwd, api_ut)
    auth_data = json_or_text(auth_resp)
    bearer = auth_data.get("accessToken") if auth_resp.ok and isinstance(auth_data, dict) else None
    if not bearer:
        detail = f"Αποτυχία Ergani API login ({auth_resp.status_code})"
        log.error(detail)
        return {"success": False, "work_date": work_date_iso, "submitted": 0, "failed": len(plan), "detail": detail, "plan": plan, "skipped": skipped}

    submitted = 0
    failures: list[dict[str, Any]] = []
    from app.submission_identity import server_submission_identity
    submission_ip, executor_instance = server_submission_identity()
    for idx, item in enumerate(plan, 1):
        emp_afm = norm_afm(item["employee_afm"])
        if idx > 1:
            delay_seconds = _auto_close_queue_delay_seconds()
            if delay_seconds > 0:
                log.info(
                    (
                        "Αναμονή πριν το επόμενο αυτόματο κλείσιμο "
                        f"({delay_seconds} δευτ.)"
                    ),
                    delay_seconds=delay_seconds,
                    batch_index=idx,
                    batch_total=len(plan),
                    employee_afm=emp_afm,
                )
                time.sleep(delay_seconds)
        event_date = str(item.get("event_date_iso") or item["reference_date"]).strip()[:10]
        event_at = f"{event_date}T{item['retro_time']}:00"
        event = str(item.get("event") or "check_out").strip() or "check_out"
        if event == "check_out" and not has_entry_for_checkout(
            employer_afm=ctx["employer_afm"],
            branch_aa=ctx["branch_aa"],
            employee_afm=emp_afm,
            reference_date_iso=str(item["reference_date"]),
            event_at=event_at,
        ):
            failures.append({**item, "error": "χωρίς πραγματική/κάρτα είσοδο"})
            continue
        try:
            payload = build_wrk_card_se_payload(
                employer_afm=ctx["employer_afm"],
                branch_aa=ctx["branch_aa"],
                employee_afm=emp_afm,
                employee_last_name=item["employee_last_name"],
                employee_first_name=item["employee_first_name"],
                event=event,
                reference_date=item["reference_date"],
                event_at=event_at,
                aitiologia=RETRO_AITIOLOGIA_INTERNET,
                comments="erganiOS automatic last-day close",
            )
        except WorkCardPayloadError as ex:
            failures.append({**item, "error": str(ex)})
            continue
        resp = client.document_submit(SUBMISSION_CODE_WRK_CARD, payload, bearer)
        parsed = json_or_text(resp)
        aitiologia_retry = False
        # Αν η Ergani απαγορεύει λόγο καθυστέρησης (ώρα εντός ορίου), ξαναστέλνουμε χωρίς αιτιολογία.
        if not resp.ok and ergani_forbids_aitiologia(parsed):
            try:
                payload = build_wrk_card_se_payload(
                    employer_afm=ctx["employer_afm"],
                    branch_aa=ctx["branch_aa"],
                    employee_afm=emp_afm,
                    employee_last_name=item["employee_last_name"],
                    employee_first_name=item["employee_first_name"],
                    event=event,
                    reference_date=item["reference_date"],
                    event_at=event_at,
                    aitiologia=None,
                    include_null_aitiologia=True,
                    comments="erganiOS automatic last-day close",
                )
            except WorkCardPayloadError as ex:
                failures.append({**item, "error": str(ex)})
                continue
            resp = client.document_submit(SUBMISSION_CODE_WRK_CARD, payload, bearer)
            parsed = json_or_text(resp)
            aitiologia_retry = True
            log.info(
                "Auto-close retry χωρίς αιτιολογία μετά απαγόρευση Ergani",
                employee_afm=emp_afm,
                batch_index=idx,
                retry_ok=bool(resp.ok),
            )
        body_text = response_body_text(resp)
        try:
            persist_wrk_card_submit(
                SUBMISSION_CODE_WRK_CARD,
                resp.status_code,
                bool(resp.ok),
                payload,
                body_text,
                None,
                None,
                None,
                client_device="erganiOS scheduled auto close",
                submission_channel="erganios",
                submission_ip=submission_ip,
                executor_instance=executor_instance,
            )
        except Exception as ex:
            failures.append({**item, "error": f"persist: {ex}"})
            continue
        record_audit_event(
            action="work_card_punch_submit",
            success=bool(resp.ok),
            http_status=int(resp.status_code or 0),
            store_id=sid,
            employer_afm=ctx["employer_afm"],
            branch_aa=ctx["branch_aa"],
            entity_type="employee",
            entity_id=emp_afm,
            details={
                "source": "auto_close_prev_day",
                "employee_afm": emp_afm,
                "employee_name": item.get("employee_name"),
                "event": event,
                "reference_date": item["reference_date"],
                "event_date": event_date,
                "event_at": event_at,
                "batch_index": idx,
                "batch_total": len(plan),
                "duration_minutes": item["duration_minutes"],
                "duration_source": item["duration_source"],
                "aitiologia_retry": aitiologia_retry,
                "ergani_response": parsed if not resp.ok else None,
            },
            client_device="erganiOS scheduled auto close",
        )
        if resp.ok:
            submitted += 1
            log.info(
                f"Αυτόματο κλείσιμο {idx}/{len(plan)} OK ({event}): {item['employee_name']} {item['retro_time']}",
                employee_afm=emp_afm,
                reference_date=item["reference_date"],
                event=event,
                aitiologia_retry=aitiologia_retry,
            )
        else:
            failures.append({**item, "error": body_text or str(parsed)[:500]})

    failed = len(failures)
    success = failed == 0
    log.info(
        f"Αυτόματο κλείσιμο προηγούμενης ημέρας: {submitted}/{len(plan)} υποβολές",
        submitted=submitted,
        failed=failed,
        skipped=len(skipped),
    )
    notification = _send_auto_close_notification(
        store_id=sid,
        store_name=str(cfg.get("name") or sid),
        work_date_iso=work_date_iso,
        submitted=submitted,
        failed=failed,
        skipped_count=len(skipped),
        plan_count=len(plan),
    )
    if notification.get("sent"):
        log.info(
            "Στάλθηκε ειδοποίηση αυτόματου κλεισίματος",
            telegram_sent=notification.get("telegram_sent"),
            email_sent=notification.get("email_sent"),
        )
    elif notification.get("errors"):
        log.warning(
            "Δεν στάλθηκε ειδοποίηση αυτόματου κλεισίματος",
            notification_errors=notification.get("errors"),
        )
    return {
        "success": success,
        "work_date": work_date_iso,
        "submitted": submitted,
        "failed": failed,
        "plan_count": len(plan),
        "failures": failures,
        "skipped": skipped,
        "notification": notification,
    }
