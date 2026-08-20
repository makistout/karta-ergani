# -*- coding: utf-8 -*-
"""Κανόνες ασφαλείας υποβολής χτυπημάτων κάρτας."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from app.date_util import format_date_for_ergani
from app.repo_card import card_event_exists
from app.repo_work_log_core import (
    work_log_has_hour_from,
    work_log_has_open_entry,
    work_log_open_hour_from,
)
from app.work_card_payload import (
    FUTURE_EVENT_AT_ERROR,
    WorkCardPayloadError,
    event_at_is_future,
    norm_afm,
    parse_event_at,
    tz_athens,
)

# Έξοδοι έως αυτή την ώρα (από μεσάνυχτα) δένουν στη μέρα εργασίας (*).
OVERNIGHT_EXIT_BEFORE_MINUTES = 3 * 60


def _iso_prev_day(iso_date: str) -> str | None:
    raw = str(iso_date or "").strip()[:10]
    try:
        d = datetime.strptime(raw, "%Y-%m-%d").date()
    except ValueError:
        return None
    return (d - timedelta(days=1)).isoformat()


def _iso_next_day(iso_date: str) -> str | None:
    raw = str(iso_date or "").strip()[:10]
    try:
        d = datetime.strptime(raw, "%Y-%m-%d").date()
    except ValueError:
        return None
    return (d + timedelta(days=1)).isoformat()


def _clock_to_minutes(raw: str | None) -> int | None:
    s = str(raw or "").strip()
    if not s:
        return None
    parts = s.replace(".", ":").split(":")
    try:
        h = int(parts[0])
        m = int(parts[1]) if len(parts) > 1 else 0
    except (ValueError, TypeError):
        return None
    if not (0 <= h <= 23 and 0 <= m <= 59):
        return None
    return h * 60 + m


def _entry_on_day(
    *,
    employer_afm: str,
    branch_aa: str,
    employee_afm: str,
    day_iso: str,
) -> bool:
    emp = norm_afm(employee_afm)
    day = str(day_iso or "").strip()[:10]
    if not emp or not day:
        return False
    if card_event_exists(emp, day, "0"):
        return True
    return work_log_has_hour_from(
        employer_afm,
        branch_aa,
        emp,
        format_date_for_ergani(day),
    )


def _open_entry_on_day(
    *,
    employer_afm: str,
    branch_aa: str,
    employee_afm: str,
    day_iso: str,
) -> bool:
    """Ανοιχτή είσοδος: Από χωρίς Έως, ή κάρτα in χωρίς κάρτα out."""
    emp = norm_afm(employee_afm)
    day = str(day_iso or "").strip()[:10]
    if not emp or not day:
        return False
    if card_event_exists(emp, day, "0") and not card_event_exists(emp, day, "1"):
        return True
    return work_log_has_open_entry(
        employer_afm,
        branch_aa,
        emp,
        format_date_for_ergani(day),
    )


def _open_entry_start_minutes(
    *,
    employer_afm: str,
    branch_aa: str,
    employee_afm: str,
    day_iso: str,
) -> int | None:
    hf = work_log_open_hour_from(
        employer_afm,
        branch_aa,
        norm_afm(employee_afm),
        format_date_for_ergani(day_iso),
    )
    return _clock_to_minutes(hf)


def has_entry_for_checkout(
    *,
    employer_afm: str,
    branch_aa: str,
    employee_afm: str,
    reference_date_iso: str,
    event_at: str | None = None,
) -> bool:
    """
    Έξοδος επιτρέπεται μόνο αν υπάρχει είσοδος (κάρτα f_type=0 ή πραγματική Από).

    - Κύρια ημέρα: f_reference_date (μέρα εργασίας μετά το overnight fix).
    - Legacy ορφανό: αν η ώρα εξόδου είναι ξημερώματα (< 03:00) την ίδια
      ημερολογιακή μέρα με το ref, δέχεται είσοδο της προηγούμενης.
    """
    ref = str(reference_date_iso or "").strip()[:10]
    if not ref:
        return False
    if _entry_on_day(
        employer_afm=employer_afm,
        branch_aa=branch_aa,
        employee_afm=employee_afm,
        day_iso=ref,
    ):
        return True

    event_day = ref
    event_min: int | None = None
    if event_at:
        try:
            dt = parse_event_at(event_at, ref)
            event_day = dt.astimezone(tz_athens()).date().isoformat()
            event_min = dt.hour * 60 + dt.minute
        except Exception:
            event_day = str(event_at).strip()[:10] or ref

    if (
        event_day == ref
        and event_min is not None
        and event_min < OVERNIGHT_EXIT_BEFORE_MINUTES
    ):
        prev = _iso_prev_day(ref)
        if prev and _entry_on_day(
            employer_afm=employer_afm,
            branch_aa=branch_aa,
            employee_afm=employee_afm,
            day_iso=prev,
        ):
            return True

    return False


def normalize_overnight_checkout_reference(
    *,
    employer_afm: str,
    branch_aa: str,
    employee_afm: str,
    reference_date_iso: str,
    event_at: str | None,
) -> tuple[str, str | None]:
    """
    Χειροκίνητη έξοδος πριν τις 03:00 → ίδια λογική overnight * με auto-close:
    - f_reference_date = μέρα εργασίας (είσοδος)
    - f_date / event_at = ημερολογιακή ώρα εξόδου (επόμενη μέρα αν χρειάζεται)
    """
    ref = str(reference_date_iso or "").strip()[:10]
    if not ref or not event_at:
        return ref, event_at
    try:
        dt = parse_event_at(event_at, ref)
    except (WorkCardPayloadError, ValueError, TypeError):
        return ref, event_at
    local = dt.astimezone(tz_athens())
    event_min = local.hour * 60 + local.minute
    if event_min >= OVERNIGHT_EXIT_BEFORE_MINUTES:
        return ref, event_at
    event_day = local.date().isoformat()
    prev = _iso_prev_day(event_day)
    hm = local.strftime("%H:%M:%S")

    open_prev = bool(prev) and _open_entry_on_day(
        employer_afm=employer_afm,
        branch_aa=branch_aa,
        employee_afm=employee_afm,
        day_iso=prev,
    )
    entry_prev = bool(prev) and _entry_on_day(
        employer_afm=employer_afm,
        branch_aa=branch_aa,
        employee_afm=employee_afm,
        day_iso=prev,
    )
    entry_event_day = _entry_on_day(
        employer_afm=employer_afm,
        branch_aa=branch_aa,
        employee_afm=employee_afm,
        day_iso=event_day,
    )

    # Ημερολογιακή μέρα εξόδου (π.χ. 24/07 00:54) με ανοιχτή είσοδο χθες → ref = χθες.
    if prev and (open_prev or (entry_prev and not entry_event_day)):
        if str(event_at).strip()[:10] != event_day:
            event_at = f"{event_day}T{hm}"
        return prev, event_at

    # Μέρα εργασίας ως ημερομηνία + ώρα ξημερωμάτων (Telegram / προγενέστερο με work day)
    # → κράτα ref, μετακίνησε event_at στην επόμενη ημερολογιακή μέρα.
    if event_day == ref and _open_entry_on_day(
        employer_afm=employer_afm,
        branch_aa=branch_aa,
        employee_afm=employee_afm,
        day_iso=ref,
    ):
        entry_min = _open_entry_start_minutes(
            employer_afm=employer_afm,
            branch_aa=branch_aa,
            employee_afm=employee_afm,
            day_iso=ref,
        )
        # Overnight: είσοδος αργότερα από την ώρα εξόδου, ή άγνωστη ώρα (κάρτα μόνο).
        if entry_min is None or entry_min > event_min:
            nxt = _iso_next_day(ref)
            if nxt:
                return ref, f"{nxt}T{hm}"

    return ref, event_at


def checkout_requires_entry_error() -> dict[str, Any]:
    return {
        "error": "Δεν επιτρέπεται έξοδος χωρίς είσοδο (πραγματική ή χτύπημα κάρτας).",
        "code": "checkout_without_entry",
    }


def new_card_punch_blocked_reason(
    *,
    intent: str,
    employer_afm: str,
    branch_aa: str,
    employee_afm: str,
    reference_date_iso: str,
    event_at: str | None = None,
) -> str | None:
    """
    Έλεγχος πριν από νέα δήλωση κάρτας (όχι correction).
    None = επιτρέπεται · αλλιώς λόγος απόρριψης (ίδια λογική με UI / auto-close).
    """
    key = str(intent or "").strip()
    emp = norm_afm(employee_afm)
    ref = str(reference_date_iso or "").strip()[:10]
    if not emp or not ref:
        return "Μη έγκυρη ημερομηνία ή ΑΦΜ"

    try:
        ref_day = datetime.strptime(ref, "%Y-%m-%d").date()
    except ValueError:
        return "Μη έγκυρη ημερομηνία ή ΑΦΜ"
    if ref_day > datetime.now(tz_athens()).date():
        return FUTURE_EVENT_AT_ERROR
    if event_at:
        try:
            if event_at_is_future(parse_event_at(str(event_at), ref)):
                return FUTURE_EVENT_AT_ERROR
        except (WorkCardPayloadError, ValueError):
            return "Μη έγκυρη ημερομηνία ή ΑΦΜ"

    if "check_out" in key:
        ref_use = ref
        event_use = str(event_at or "").strip() or None
        if event_use or key.endswith("_now"):
            if not event_use:
                event_use = datetime.now(tz_athens()).isoformat(timespec="seconds")
            ref_use, event_use = normalize_overnight_checkout_reference(
                employer_afm=employer_afm,
                branch_aa=branch_aa,
                employee_afm=emp,
                reference_date_iso=ref,
                event_at=event_use,
            )
        if card_event_exists(emp, ref_use, "1"):
            return "Η κάρτα έχει ήδη κλείσει (δήλωση εξόδου)"
        if not has_entry_for_checkout(
            employer_afm=employer_afm,
            branch_aa=branch_aa,
            employee_afm=emp,
            reference_date_iso=ref_use,
            event_at=event_use,
        ):
            return "Δεν επιτρέπεται έξοδος χωρίς είσοδο"
        return None

    if "check_in" in key:
        if card_event_exists(emp, ref, "0"):
            return "Η κάρτα έχει ήδη ανοίξει (δήλωση εισόδου)"
        # Αρχική may show «σε εργασία» from open πραγματική even before a local
        # WRKCardSE row exists — treat that as already open for a new check-in.
        try:
            if work_log_has_open_entry(
                employer_afm,
                branch_aa,
                emp,
                format_date_for_ergani(ref),
            ):
                return "Η κάρτα έχει ήδη ανοίξει (δήλωση εισόδου)"
        except WorkCardPayloadError:
            pass
        return None

    return None
