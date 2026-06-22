"""Κατασκευή σώματος POST Documents/WTOWeek — σταθερό εβδομαδιαίο ωράριο."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from app.date_util import format_date_for_ergani
from app.work_card_payload import WorkCardPayloadError, norm_afm

SUBMISSION_CODE_WTO_WEEK = "WTOWeek"

_VALID_TYPES = frozenset({"ΕΡΓ", "ΤΗΛ", "ΑΝ", "ΜΕ"})
_TIME_RE = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")
_ALL_DAYS = frozenset(range(7))


def _blank_field(value: str | None) -> str:
    s = str(value or "").strip()
    return s if s else " "


def _normalize_type(value: Any) -> str:
    raw = str(value or "").strip().upper()
    aliases = {"ERG": "ΕΡΓ", "TEL": "ΤΗΛ", "AN": "ΑΝ", "ME": "ΜΕ"}
    normalized = aliases.get(raw, raw)
    if normalized not in _VALID_TYPES:
        raise WorkCardPayloadError(
            f"Μη έγκυρος τύπος εβδομαδιαίου ωραρίου: {value}. "
            f"Επιτρεπτοί: {', '.join(sorted(_VALID_TYPES))}"
        )
    return normalized


def _normalize_time(value: Any, label: str) -> str:
    raw = str(value or "").strip()
    if not _TIME_RE.fullmatch(raw):
        raise WorkCardPayloadError(f"{label}: απαιτείται ώρα σε μορφή ΩΩ:ΛΛ")
    return raw


def _parse_iso_date(value: str, label: str) -> datetime:
    try:
        return datetime.strptime(str(value or "").strip()[:10], "%Y-%m-%d")
    except ValueError as ex:
        raise WorkCardPayloadError(f"{label}: μη έγκυρη ημερομηνία") from ex


def _normalize_day_entries(day: int, entries: Any) -> list[dict[str, str]]:
    if not isinstance(entries, list) or not entries:
        raise WorkCardPayloadError(f"Η ημέρα {day} πρέπει να έχει τουλάχιστον μία εγγραφή")

    analytics: list[dict[str, str]] = []
    rest_types: set[str] = set()
    interval_types: set[str] = set()
    intervals: list[tuple[str, str]] = []

    for index, entry in enumerate(entries, start=1):
        if not isinstance(entry, dict):
            raise WorkCardPayloadError(f"Ημέρα {day}, εγγραφή {index}: αναμενόταν αντικείμενο")
        entry_type = _normalize_type(entry.get("type") or entry.get("f_type"))
        if entry_type in {"ΑΝ", "ΜΕ"}:
            rest_types.add(entry_type)
            analytics.append({"f_type": entry_type, "f_from": " ", "f_to": " "})
            continue

        interval_types.add(entry_type)
        hour_from = _normalize_time(
            entry.get("from") or entry.get("f_from"),
            f"Ημέρα {day}, εγγραφή {index}, ώρα από",
        )
        hour_to = _normalize_time(
            entry.get("to") or entry.get("f_to"),
            f"Ημέρα {day}, εγγραφή {index}, ώρα έως",
        )
        if hour_from == hour_to:
            raise WorkCardPayloadError(
                f"Ημέρα {day}, εγγραφή {index}: η ώρα από και η ώρα έως δεν μπορούν να είναι ίδιες"
            )
        intervals.append((hour_from, hour_to))
        analytics.append({"f_type": entry_type, "f_from": hour_from, "f_to": hour_to})

    if rest_types and interval_types:
        raise WorkCardPayloadError(
            f"Ημέρα {day}: Ανάπαυση/Μη εργασία δεν συνδυάζεται με Εργασία/Τηλεργασία"
        )
    if rest_types and len(analytics) != 1:
        raise WorkCardPayloadError(
            f"Ημέρα {day}: η Ανάπαυση ή Μη εργασία πρέπει να είναι η μοναδική εγγραφή"
        )

    # Επιτρέπεται νυχτερινό διάστημα (π.χ. 22:00–06:00), άρα ο έλεγχος
    # επικάλυψης εφαρμόζεται μόνο σε διαστήματα που λήγουν την ίδια ημέρα.
    same_day = sorted((start, end) for start, end in intervals if end > start)
    for previous, current in zip(same_day, same_day[1:]):
        if current[0] < previous[1]:
            raise WorkCardPayloadError(f"Ημέρα {day}: τα χρονικά διαστήματα επικαλύπτονται")

    return analytics


def build_wto_week_payload(
    *,
    branch_aa: str,
    employee_afm: str,
    employee_last_name: str,
    employee_first_name: str,
    from_date: str,
    days: list[dict[str, Any]],
    to_date: str | None = None,
    comments: str | None = None,
) -> dict[str, Any]:
    emp = norm_afm(employee_afm)
    last = str(employee_last_name or "").strip()
    first = str(employee_first_name or "").strip()
    if not last or not first:
        raise WorkCardPayloadError("Απαιτούνται επώνυμο και όνομα εργαζομένου")
    if not isinstance(days, list):
        raise WorkCardPayloadError("Απαιτείται λίστα επτά ημερών")

    start = _parse_iso_date(from_date, "Ημερομηνία έναρξης")
    end = _parse_iso_date(to_date, "Ημερομηνία λήξης") if to_date else None
    if end and end < start:
        raise WorkCardPayloadError("Η ημερομηνία λήξης δεν μπορεί να προηγείται της έναρξης")

    by_day: dict[int, list[dict[str, str]]] = {}
    for row in days:
        if not isinstance(row, dict):
            raise WorkCardPayloadError("Κάθε ημέρα πρέπει να είναι αντικείμενο")
        try:
            day = int(row.get("day"))
        except (TypeError, ValueError) as ex:
            raise WorkCardPayloadError("Μη έγκυρος κωδικός ημέρας") from ex
        if day in by_day:
            raise WorkCardPayloadError(f"Η ημέρα {day} δηλώθηκε περισσότερες από μία φορές")
        by_day[day] = _normalize_day_entries(day, row.get("entries"))

    if set(by_day) != _ALL_DAYS:
        missing = sorted(_ALL_DAYS - set(by_day))
        extra = sorted(set(by_day) - _ALL_DAYS)
        detail = []
        if missing:
            detail.append(f"λείπουν ημέρες {missing}")
        if extra:
            detail.append(f"μη έγκυρες ημέρες {extra}")
        raise WorkCardPayloadError("Απαιτούνται ακριβώς οι ημέρες 0–6 (" + ", ".join(detail) + ")")

    employee_rows = [
        {
            "f_afm": emp,
            "f_eponymo": last[:50],
            "f_onoma": first[:30],
            "f_day": str(day),
            "ErgazomenosAnalytics": {
                "ErgazomenosWTOAnalytics": by_day[day],
            },
        }
        for day in (1, 2, 3, 4, 5, 6, 0)
    ]

    return {
        "WTOS": {
            "WTO": [
                {
                    "f_aa_pararthmatos": str(branch_aa or "0").strip()[:5] or "0",
                    "f_rel_protocol": " ",
                    "f_rel_date": " ",
                    "f_comments": str(comments or "").strip()[:200] or None,
                    "f_from_date": format_date_for_ergani(from_date),
                    "f_to_date": format_date_for_ergani(to_date) if to_date else " ",
                    "Ergazomenoi": {"ErgazomenoiWTO": employee_rows},
                }
            ]
        }
    }


__all__ = ["SUBMISSION_CODE_WTO_WEEK", "build_wto_week_payload"]
