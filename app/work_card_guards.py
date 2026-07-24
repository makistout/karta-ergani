# -*- coding: utf-8 -*-
"""Κανόνες ασφαλείας υποβολής χτυπημάτων κάρτας."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from app.date_util import format_date_for_ergani
from app.repo_card import card_event_exists
from app.repo_work_log_core import work_log_has_hour_from
from app.work_card_payload import norm_afm, parse_event_at, tz_athens


def _iso_prev_day(iso_date: str) -> str | None:
    raw = str(iso_date or "").strip()[:10]
    try:
        d = datetime.strptime(raw, "%Y-%m-%d").date()
    except ValueError:
        return None
    return (d - timedelta(days=1)).isoformat()


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

    # Ξημερώματα με ref = ημέρα εξόδου (παλιό orphan style): είσοδος χθες.
    if event_day == ref and event_min is not None and event_min < 3 * 60:
        prev = _iso_prev_day(ref)
        if prev and _entry_on_day(
            employer_afm=employer_afm,
            branch_aa=branch_aa,
            employee_afm=employee_afm,
            day_iso=prev,
        ):
            return True

    return False


def checkout_requires_entry_error() -> dict[str, Any]:
    return {
        "error": "Δεν επιτρέπεται έξοδος χωρίς είσοδο (πραγματική ή χτύπημα κάρτας).",
        "code": "checkout_without_entry",
    }
