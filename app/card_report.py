"""
Αναφορά κατάστασης κάρτας εργασίας: ψηφιακό ωράριο + πραγματική απασχόληση + δηλώσεις WRKCardSE.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from app.date_util import format_date_for_ergani, format_f_date_time
from app.repo_card import list_card_events_for_store_date
from app.repo_entities import flex_arrival_map_for_employer
from app.repo_schedule import list_schedule_for_store
from app.repo_work_log import _attach_card_punch_hint, list_work_log_for_store
from app.work_card_payload import tz_athens

# Πρώτα όσοι δουλεύουν / ολοκλήρωσαν βάρδια, στο τέλος ρεπό και λοιποί.
_STATUS_ORDER = {
    "at_work": 0,
    "needs_checkout": 1,
    "completed": 2,
    "late_arrival": 3,
    "needs_checkin": 4,
    "unscheduled_work": 5,
    "absent": 6,
    "pending": 7,
    "no_schedule": 8,
    "rest": 9,
}

_REST_MARKERS = ("ΑΝΑΠΑΥΣΗ", "ΡΕΠΟ", "ΜΗ ΕΡΓΑΣΙΑ", "ΑΔΕΙΑ", "ΑΡΓΙΑ")


def _parse_hm(value: str | None) -> tuple[int, int] | None:
    m = re.match(r"^(\d{1,2}):(\d{2})", (value or "").strip().rstrip("*"))
    if not m:
        return None
    return int(m.group(1)), int(m.group(2))


def _hm_to_minutes(value: str | None) -> int | None:
    p = _parse_hm(value)
    if not p:
        return None
    return p[0] * 60 + p[1]


def _timeline_minutes(
    hm_value: str | None,
    *,
    day_anchor: str | None = None,
    is_next_day: bool | int | None = None,
) -> int | None:
    """Λεπτά από μεσάνυχτα ημέρας εργασίας — +1440 αν η ώρα είναι την επόμενη μέρα."""
    mins = _hm_to_minutes(hm_value)
    if mins is None:
        return None
    raw = (hm_value or "").strip()
    next_day = is_next_day in (1, True, "1")
    if not next_day and raw.endswith("*"):
        next_day = True
    if not next_day and day_anchor:
        anchor = _hm_to_minutes(day_anchor)
        if anchor is not None and mins < anchor:
            next_day = True
    return mins + (24 * 60 if next_day else 0)


def _schedule_end_timeline(sched_from: str | None, sched_to: str | None) -> int | None:
    s_end = _hm_to_minutes(sched_to)
    if s_end is None:
        return None
    s_start = _hm_to_minutes(sched_from)
    if s_start is not None and s_end <= s_start:
        s_end += 24 * 60
    return s_end


def _minutes_now_on_date(work_date_ergani: str) -> int:
    parts = (work_date_ergani or "").strip().split("/")
    if len(parts) != 3:
        now = datetime.now(tz_athens())
        return now.hour * 60 + now.minute
    try:
        d, m, y = int(parts[0]), int(parts[1]), int(parts[2])
        if y < 100:
            y += 2000
        ref = datetime(y, m, d, tzinfo=tz_athens()).date()
    except ValueError:
        now = datetime.now(tz_athens())
        return now.hour * 60 + now.minute
    today = datetime.now(tz_athens()).date()
    if ref != today:
        return 24 * 60 if ref < today else 0
    now = datetime.now(tz_athens())
    return now.hour * 60 + now.minute


def _is_rest_day(shift_type: str | None, hour_from: str | None, hour_to: str | None) -> bool:
    st = (shift_type or "").upper()
    if any(marker in st for marker in _REST_MARKERS):
        return True
    hf, ht = (hour_from or "").strip(), (hour_to or "").strip()
    if not hf and not ht and st:
        return True
    return False


def _card_time_label(f_date: str | None) -> str | None:
    """Ώρα κίνησης κάρτας — όπως ergani (HH:MM:SS από ISO f_date)."""
    if not f_date:
        return None
    label = format_f_date_time(f_date)
    if label:
        return label
    p = _parse_hm(str(f_date))
    return f"{p[0]:02d}:{p[1]:02d}" if p else None


def _card_hm_short(card_ev: dict[str, Any] | None) -> str | None:
    """Ώρα κάρτας HH:mm για WTODaily."""
    label = _card_time_label((card_ev or {}).get("f_date"))
    if not label:
        return None
    p = _parse_hm(label)
    return f"{p[0]:02d}:{p[1]:02d}" if p else None


def _hm_short(value: str | None) -> str | None:
    p = _parse_hm(value)
    return f"{p[0]:02d}:{p[1]:02d}" if p else None


def _has_work_signal(
    card_in: dict[str, Any] | None,
    card_out: dict[str, Any] | None,
    wl: dict[str, Any] | None,
) -> bool:
    if card_in or card_out:
        return True
    wf = ((wl or {}).get("hour_from") or "").strip()
    wt = ((wl or {}).get("hour_to") or "").strip()
    dash = "—"
    return bool(wf and wf != dash) or bool(wt and wt != dash)


def _has_card_punch(
    card_in: dict[str, Any] | None,
    card_out: dict[str, Any] | None,
) -> bool:
    return bool(card_in or card_out)


def _has_arrival_signal(
    card_in: dict[str, Any] | None,
    wl: dict[str, Any] | None,
) -> bool:
    if card_in:
        return True
    wf = ((wl or {}).get("hour_from") or "").strip()
    return bool(wf and wf != "—")


def _has_departure_signal(
    card_out: dict[str, Any] | None,
    wl: dict[str, Any] | None,
) -> bool:
    if card_out:
        return True
    wt = ((wl or {}).get("hour_to") or "").strip()
    return bool(wt and wt != "—")


def _rest_day_row_eval(
    *,
    card_in: dict[str, Any] | None,
    card_out: dict[str, Any] | None,
    wl: dict[str, Any] | None,
) -> tuple[str, str, str]:
    """Ενέργεια, status, status_label για ημέρα ρεπό/ανάπαυση."""
    label = "Ανάπαυση / ρεπό"
    if not _has_work_signal(card_in, card_out, wl):
        return "Δεν απαιτείται δήλωση κάρτας", "rest", label
    has_arrival = _has_arrival_signal(card_in, wl)
    has_departure = _has_departure_signal(card_out, wl)
    if has_arrival and not has_departure:
        return (
            "Στο τέλος βάρδιας: δήλωση αποχώρησης (έξοδος)",
            "needs_checkout",
            label,
        )
    if has_arrival and has_departure:
        return "—", "completed", "Ολοκληρωμένη μέρα"
    return "Ελέγξτε κάρτα και ημερολόγιο πραγματικής απασχόλησης", "rest", label


_EARLY_CARD_MINUTES = 60


def _wto_daily_fix(
    *,
    sched: dict[str, Any] | None,
    card_in: dict[str, Any] | None,
    card_out: dict[str, Any] | None,
    wl: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """
    Πρόταση υποβολής WTODaily όταν:
    - δεν υπάρχει ψηφιακό ωράριο (χωρίς κάρτα/πραγματική), ή
    - ρεπό/ανάπαυση (χωρίς κάρτα/πραγματική), ή
    - πραγματική ≥1 ώρα πριν το ωράριο (μόνο χωρίς χτύπημα κάρτας).
    """
    if _has_work_signal(card_in, card_out, wl):
        return None

    card_in_hm = _card_hm_short(card_in)
    card_out_hm = _card_hm_short(card_out)
    wl_in_hm = _hm_short((wl or {}).get("hour_from"))
    wl_out_hm = _hm_short((wl or {}).get("hour_to"))
    arrival_hm = card_in_hm or wl_in_hm

    if not sched:
        return {
            "eligible": True,
            "kind": "no_schedule",
            "schedule_type": "ΕΡΓ",
            "hour_from": "",
            "hour_to": "",
            "action": "Αλλαγή ωραρίου (WTODaily) — δεν υπάρχει ψηφιακό ωράριο",
            "note": "Δεν υπάρχει εγγραφή ψηφιακού ωραρίου για αυτή την ημέρα.",
        }

    shift_type = (sched or {}).get("shift_type")
    sched_from = (sched or {}).get("hour_from")
    sched_to = (sched or {}).get("hour_to")

    if _is_rest_day(shift_type, sched_from, sched_to):
        return {
            "eligible": True,
            "kind": "rest_day",
            "schedule_type": "ΕΡΓ",
            "hour_from": "",
            "hour_to": "",
            "action": "Αλλαγή ωραρίου (WTODaily) — ημέρα ρεπό/ανάπαυση",
            "note": "Το ψηφιακό ωράριο δηλώνει ανάπαυση/ρεπό.",
        }

    if not _is_rest_day(shift_type, sched_from, sched_to) and sched_from and arrival_hm:
        arrival_m = _hm_to_minutes(arrival_hm)
        s_start = _hm_to_minutes(sched_from)
        if (
            arrival_m is not None
            and s_start is not None
            and arrival_m <= s_start - _EARLY_CARD_MINUTES
        ):
            src = "πραγματική"
            return {
                "eligible": True,
                "kind": "early_card",
                "schedule_type": "ΕΡΓ",
                "hour_from": arrival_hm,
                "hour_to": (sched_to or "").strip(),
                "action": (
                    f"Τροποποίηση ωραρίου (WTODaily) — {src} {arrival_hm} "
                    f"≥1 ώρα πριν από {sched_from}"
                ),
                "note": (
                    f"Η είσοδος ({arrival_hm} από {src}) είναι ≥1 ώρα πριν το ωράριο ({sched_from})."
                ),
            }

    return None


def _pick_name(*pairs: tuple[str | None, str | None]) -> tuple[str, str]:
    for ep, on in pairs:
        if (ep or "").strip() or (on or "").strip():
            return (ep or "").strip(), (on or "").strip()
    return "", ""


def _schedule_shows_blank(schedule: dict[str, Any] | None) -> bool:
    """True όταν στη στήλη «Ψηφ. ωράριο» θα εμφανιστεί «—» (χωρίς ώρες/τύπο βάρδιας)."""
    if not schedule:
        return True
    hf = (schedule.get("hour_from") or "").strip()
    ht = (schedule.get("hour_to") or "").strip()
    if hf or ht:
        return False
    st = (schedule.get("shift_type") or "").strip()
    return not st


def _flex_tolerance_minutes(flex_arrival_minutes: int | None, *, default: int = 15) -> int:
    if flex_arrival_minutes is None:
        return default
    return max(0, int(flex_arrival_minutes))


def _is_leave_eligible(
    *,
    sched: dict[str, Any] | None,
    wl: dict[str, Any] | None,
    card_in: dict[str, Any] | None,
    card_out: dict[str, Any] | None,
    s_start: int | None,
    now_min: int,
    tol: int,
) -> bool:
    if not sched:
        return False
    shift_type = (sched or {}).get("shift_type")
    sched_from = (sched or {}).get("hour_from")
    sched_to = (sched or {}).get("hour_to")
    if _is_rest_day(shift_type, sched_from, sched_to):
        return False
    has_arrival = bool(card_in) or bool((wl or {}).get("hour_from"))
    has_departure = bool(card_out) or bool((wl or {}).get("hour_to"))
    if has_departure and not has_arrival:
        return False
    if has_arrival:
        return False
    if s_start is None:
        return False
    return now_min > s_start + tol + 1


def _evaluate_row(
    *,
    sched: dict[str, Any] | None,
    wl: dict[str, Any] | None,
    card_in: dict[str, Any] | None,
    card_out: dict[str, Any] | None,
    work_date_ergani: str,
    flex_arrival_minutes: int | None = None,
    late_tolerance_min: int = 15,
) -> dict[str, Any]:
    tol = _flex_tolerance_minutes(
        flex_arrival_minutes,
        default=late_tolerance_min,
    )
    notes: list[str] = []
    shift_type = (sched or {}).get("shift_type")
    sched_from = (sched or {}).get("hour_from")
    sched_to = (sched or {}).get("hour_to")
    actual_from = (wl or {}).get("hour_from")
    actual_to = (wl or {}).get("hour_to")

    card_block: dict[str, Any] = {
        "check_in": _card_time_label((card_in or {}).get("f_date")),
        "check_out": _card_time_label((card_out or {}).get("f_date")),
        "has_check_in": bool(card_in),
        "has_check_out": bool(card_out),
    }

    if sched and _is_rest_day(shift_type, sched_from, sched_to):
        wto_fix = _wto_daily_fix(
            sched=sched, card_in=card_in, card_out=card_out, wl=wl
        )
        rest_action, rest_status, rest_label = _rest_day_row_eval(
            card_in=card_in, card_out=card_out, wl=wl
        )
        rest_notes = list(notes)
        if wto_fix:
            rest_notes.append(str(wto_fix.get("note") or ""))
        if card_in and not _has_departure_signal(card_out, wl):
            note = "Υπάρχει δήλωση εισόδου στην κάρτα, όχι ακόμα έξοδος"
            if note not in rest_notes:
                rest_notes.append(note)
        return {
            "status": rest_status,
            "status_label": rest_label,
            "action": (wto_fix or {}).get("action") or rest_action,
            "notes": rest_notes,
            "card": card_block,
            "leave_eligible": False,
            "wto_daily": wto_fix,
        }

    now_min = _minutes_now_on_date(work_date_ergani)
    s_start = _hm_to_minutes(sched_from)
    s_end = _schedule_end_timeline(sched_from, sched_to)
    a_start = _hm_to_minutes(actual_from)
    a_end = _timeline_minutes(
        actual_to,
        day_anchor=actual_from,
        is_next_day=(wl or {}).get("is_end_date_different"),
    )
    leave_eligible = _is_leave_eligible(
        sched=sched,
        wl=wl,
        card_in=card_in,
        card_out=card_out,
        s_start=s_start,
        now_min=now_min,
        tol=tol,
    )

    if not sched and (a_start is not None or card_in or card_out):
        wto_fix = _wto_daily_fix(
            sched=None, card_in=card_in, card_out=card_out, wl=wl
        )
        unsched_notes = list(notes)
        if wto_fix:
            unsched_notes.append(str(wto_fix.get("note") or ""))
        return {
            "status": "unscheduled_work",
            "status_label": "Χωρίς ωράριο",
            "action": (wto_fix or {}).get("action")
            or "Ελέγξτε ψηφιακό ωράριο ή καταχώρηση στην κάρτα",
            "notes": unsched_notes,
            "card": card_block,
            "leave_eligible": False,
            "wto_daily": wto_fix,
        }

    if not sched:
        wto_fix = _wto_daily_fix(
            sched=None, card_in=card_in, card_out=card_out, wl=wl
        )
        no_sched_notes = list(notes)
        if wto_fix:
            no_sched_notes.append(str(wto_fix.get("note") or ""))
        return {
            "status": "no_schedule",
            "status_label": "Χωρίς εγγραφή ωραρίου",
            "action": (wto_fix or {}).get("action") or "Συγχρονίστε το ψηφιακό ωράριο",
            "notes": no_sched_notes,
            "card": card_block,
            "leave_eligible": False,
            "wto_daily": wto_fix,
        }

    if card_in and not a_start:
        notes.append("Υπάρχει δήλωση εισόδου στην κάρτα, όχι ακόμα στο ημερολόγιο πραγματικής απασχόλησης")
    if card_out and not a_end:
        notes.append("Υπάρχει δήλωση εξόδου στην κάρτα, χωρίς ώρα λήξης στο ημερολόγιο")

    if a_start is not None and a_end is not None:
        if s_start is not None and a_start > s_start + tol:
            notes.append(
                f"Καθυστέρηση άφιξης (ωράριο {sched_from}, πραγματική {actual_from}, ευελ. {tol}′)"
            )
        if s_end is not None and a_end < s_end - tol:
            notes.append(
                f"Πρόωρη αποχώρηση (ωράριο {sched_to}, πραγματική {actual_to}, ευελ. {tol}′)"
            )
        return {
            "status": "completed",
            "status_label": "Ολοκληρωμένη μέρα",
            "action": "—",
            "notes": notes,
            "card": card_block,
            "leave_eligible": False,
        }

    if a_start is not None and a_end is None:
        if s_end is not None and now_min >= s_end:
            return {
                "status": "needs_checkout",
                "status_label": "Αναμένεται έξοδος",
                "action": "Να δηλωθεί αποχώρηση (έξοδος) στην κάρτα εργασίας",
                "notes": notes,
                "card": card_block,
                "leave_eligible": False,
            }
        return {
            "status": "at_work",
            "status_label": "Σε εργασία",
            "action": "Στο τέλος βάρδιας: δήλωση αποχώρησης (έξοδος)",
            "notes": notes,
            "card": card_block,
            "leave_eligible": False,
        }

    if a_start is None:
        leave_action = (
            "Δήλωση ρεπό (WTODaily) ή άδειας (WTOLeave) — πέραν ευελιξίας προσέλευσης"
            if leave_eligible
            else None
        )
        if s_start is not None and now_min < s_start - 30:
            return {
                "status": "pending",
                "status_label": "Εκκρεμεί έναρξη",
                "action": f"Προσέλευση (είσοδος) πριν/στις {sched_from or '—'}",
                "notes": notes,
                "card": card_block,
                "leave_eligible": False,
            }
        if s_end is not None and now_min > s_end:
            return {
                "status": "absent",
                "status_label": "Δεν καταγράφεται άφιξη",
                "action": leave_action or "Ελέγξτε κάρτα και ημερολόγιο πραγματικής απασχόλησης",
                "notes": notes,
                "card": card_block,
                "leave_eligible": leave_eligible,
                "rest_declare_eligible": leave_eligible,
            }
        if s_start is not None and now_min > s_start + tol:
            return {
                "status": "late_arrival",
                "status_label": "Καθυστερημένη άφιξη",
                "action": leave_action or "Να δηλωθεί προσέλευση (είσοδος) στην κάρτα εργασίας",
                "notes": notes,
                "card": card_block,
                "leave_eligible": leave_eligible,
                "rest_declare_eligible": leave_eligible,
            }
        return {
            "status": "needs_checkin",
            "status_label": "Αναμένεται είσοδος",
            "action": "Να δηλωθεί προσέλευση (είσοδος) στην κάρτα εργασίας",
            "notes": notes,
            "card": card_block,
            "leave_eligible": leave_eligible,
            "rest_declare_eligible": False,
        }

    return {
        "status": "pending",
        "status_label": "Εκκρεμεί",
        "action": "Ελέγξτε ωράριο και κάρτα",
        "notes": notes,
        "card": card_block,
        "leave_eligible": False,
    }


def _card_punch_fields(
    sched: dict[str, Any] | None,
    wl: dict[str, Any] | None,
) -> dict[str, Any]:
    """Ένδειξη προγενέστερου χτυπήματος κάρτας από ψηφιακό ωράριο."""
    punch_row: dict[str, Any] = {
        "hour_from": (wl or {}).get("hour_from"),
        "hour_to": (wl or {}).get("hour_to"),
    }
    slots = [sched] if sched else []
    _attach_card_punch_hint(punch_row, slots)
    if not punch_row.get("needs_card_punch"):
        return {}
    return {
        "needs_card_punch": True,
        "card_event": punch_row.get("card_event"),
        "retro_time": punch_row.get("retro_time"),
    }


def build_card_status_report(
    employer_afm: str,
    branch_aa: str,
    *,
    date_iso: str | None = None,
) -> dict[str, Any]:
    work_date = format_date_for_ergani(date_iso)
    ref_iso = (date_iso or datetime.now(tz_athens()).date().isoformat())[:10]

    schedule_rows = list_schedule_for_store(employer_afm, branch_aa, work_date)
    work_log_rows = list_work_log_for_store(employer_afm, branch_aa, work_date)
    card_events = list_card_events_for_store_date(
        employer_afm, branch_aa, ref_iso
    )
    flex_by_afm = flex_arrival_map_for_employer(employer_afm, branch_aa)

    sched_by_afm: dict[str, dict[str, Any]] = {}
    for row in schedule_rows:
        afm = (row.get("employee_afm") or "").strip()
        if afm and afm not in sched_by_afm:
            sched_by_afm[afm] = row

    wl_by_afm: dict[str, dict[str, Any]] = {}
    for row in work_log_rows:
        afm = (row.get("employee_afm") or "").strip()
        if afm and afm not in wl_by_afm:
            wl_by_afm[afm] = row

    card_in: dict[str, dict[str, Any]] = {}
    card_out: dict[str, dict[str, Any]] = {}
    for ev in card_events:
        afm = (ev.get("f_afm") or "").strip()
        if not afm:
            continue
        ft = str(ev.get("f_type") or "").strip()
        if ft == "0":
            card_in[afm] = ev
        elif ft == "1":
            card_out[afm] = ev

    all_afms = sorted(
        set(sched_by_afm) | set(wl_by_afm) | set(card_in) | set(card_out),
        key=lambda a: (
            sched_by_afm.get(a, {}).get("eponymo")
            or wl_by_afm.get(a, {}).get("eponymo")
            or a
        ),
    )

    rows_out: list[dict[str, Any]] = []
    summary: dict[str, int] = {
        "total": 0,
        "needs_checkin": 0,
        "needs_checkout": 0,
        "at_work": 0,
        "completed": 0,
        "rest": 0,
        "absent": 0,
        "late_arrival": 0,
        "other": 0,
    }

    for afm in all_afms:
        sched = sched_by_afm.get(afm)
        wl = wl_by_afm.get(afm)
        ep, on = _pick_name(
            ((sched or {}).get("eponymo"), (sched or {}).get("onoma")),
            ((wl or {}).get("eponymo"), (wl or {}).get("onoma")),
            (
                (card_in.get(afm) or {}).get("f_eponymo"),
                (card_in.get(afm) or {}).get("f_onoma"),
            ),
            (
                (card_out.get(afm) or {}).get("f_eponymo"),
                (card_out.get(afm) or {}).get("f_onoma"),
            ),
        )
        flex_min = flex_by_afm.get(afm)
        if flex_min is None and sched:
            flex_min = sched.get("flex_arrival_minutes")
        if flex_min is None and wl:
            flex_min = wl.get("flex_arrival_minutes")
        ev = _evaluate_row(
            sched=sched,
            wl=wl,
            card_in=card_in.get(afm),
            card_out=card_out.get(afm),
            work_date_ergani=work_date,
            flex_arrival_minutes=flex_min,
        )
        st = ev["status"]
        summary["total"] += 1
        if st in summary:
            summary[st] += 1
        else:
            summary["other"] += 1

        wto_fix = ev.get("wto_daily")
        if not wto_fix:
            wto_fix = _wto_daily_fix(
                sched=sched,
                card_in=card_in.get(afm),
                card_out=card_out.get(afm),
                wl=wl,
            )
        row_notes = list(ev.get("notes") or [])
        row_action = ev["action"]
        if wto_fix and wto_fix.get("kind") in ("early_card", "rest_day", "no_schedule"):
            note = str(wto_fix.get("note") or "")
            if note and note not in row_notes:
                row_notes.append(note)
            row_action = str(wto_fix.get("action") or row_action)

        rows_out.append({
            "employee_afm": afm,
            "eponymo": ep,
            "onoma": on,
            "work_date": work_date,
            "flex_arrival_minutes": flex_min,
            "schedule": (
                {
                    "hour_from": sched.get("hour_from"),
                    "hour_to": sched.get("hour_to"),
                    "shift_type": sched.get("shift_type"),
                }
                if sched
                else None
            ),
            "work_log": (
                {
                    "hour_from": wl.get("hour_from"),
                    "hour_to": wl.get("hour_to"),
                }
                if wl
                else None
            ),
            "card": ev["card"],
            "status": st,
            "status_label": ev["status_label"],
            "action": row_action,
            "notes": row_notes,
            "leave_eligible": bool(ev.get("leave_eligible")),
            "rest_declare_eligible": bool(ev.get("rest_declare_eligible")),
            "wto_daily_eligible": bool(wto_fix and wto_fix.get("eligible")),
            "wto_daily": wto_fix,
            **_card_punch_fields(sched, wl),
        })

    rows_out.sort(
        key=lambda r: (
            1 if _schedule_shows_blank(r.get("schedule")) else 0,
            _STATUS_ORDER.get(r["status"], 99),
            (r.get("eponymo") or "").upper(),
            r.get("employee_afm") or "",
        )
    )

    return {
        "date": ref_iso,
        "work_date": work_date,
        "summary": summary,
        "rows": rows_out,
        "meta": {
            "schedule_count": len(schedule_rows),
            "work_log_count": len(work_log_rows),
            "card_event_count": len(card_events),
            "has_schedule": bool(schedule_rows),
            "has_work_log": bool(work_log_rows),
        },
    }
