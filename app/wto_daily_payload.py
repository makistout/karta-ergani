"""Κατασκευή σώματος POST Documents/WTODaily — ημερήσιο τροποποιούμενο ωράριο."""

from __future__ import annotations

from typing import Any

from app.date_util import format_date_for_ergani
from app.work_card_payload import WorkCardPayloadError, norm_afm

SUBMISSION_CODE_WTO_DAILY = "WTODaily"

_VALID_TYPES = frozenset({"ΕΡΓ", "ΤΗΛ", "ΑΝ", "ΜΕ"})


def _blank_field(value: str | None) -> str:
    s = (value or "").strip()
    return s if s else " "


SUBMISSION_CODE_WTO_DAILY_A = "WTODailyA"


def _schedule_analytics(
    *,
    schedule_type: str,
    hour_from: str | None,
    hour_to: str | None,
    intervals: list[dict[str, Any]] | None,
) -> list[dict[str, str]]:
    stype = str(schedule_type or "ΕΡΓ").strip().upper()
    if stype == "ERG":
        stype = "ΕΡΓ"
    if stype not in _VALID_TYPES:
        raise WorkCardPayloadError(
            f"Μη έγκυρος τύπος ωραρίου: {schedule_type}. "
            f"Επιτρεπτοί: {', '.join(sorted(_VALID_TYPES))}"
        )

    if intervals and stype != "ΑΝ":
        analytics: list[dict[str, str]] = []
        for item in intervals:
            hf = str((item or {}).get("hour_from") or "").strip()
            ht = str((item or {}).get("hour_to") or "").strip()
            if not hf and not ht:
                continue
            if not hf or not ht:
                raise WorkCardPayloadError("Στο σπαστό ωράριο κάθε διάστημα θέλει ώρα από και έως")
            analytics.append({"f_type": stype, "f_from": _blank_field(hf), "f_to": _blank_field(ht)})
        if not analytics:
            analytics = [{"f_type": stype, "f_from": _blank_field(hour_from), "f_to": _blank_field(hour_to)}]
        return analytics
    return [{"f_type": stype, "f_from": _blank_field(hour_from), "f_to": _blank_field(hour_to)}]


def _employee_wto_daily_block(
    *,
    employee_afm: str,
    employee_last_name: str,
    employee_first_name: str,
    reference_date: str,
    schedule_type: str = "ΕΡΓ",
    hour_from: str | None = None,
    hour_to: str | None = None,
    intervals: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    emp = norm_afm(employee_afm)
    ep = (employee_last_name or "").strip()
    on = (employee_first_name or "").strip()
    if not ep or not on:
        raise WorkCardPayloadError("Απαιτούνται επώνυμο και όνομα εργαζομένου")
    ergani_date = format_date_for_ergani(reference_date)
    return {
        "f_afm": emp,
        "f_eponymo": ep,
        "f_onoma": on,
        "f_date": ergani_date,
        "ErgazomenosAnalytics": {
            "ErgazomenosWTOAnalytics": _schedule_analytics(
                schedule_type=schedule_type,
                hour_from=hour_from,
                hour_to=hour_to,
                intervals=intervals,
            ),
        },
    }


def _wto_envelope_from_employees(
    *,
    branch_aa: str,
    employee_blocks: list[dict[str, Any]],
    comments: str | None = None,
) -> dict[str, Any]:
    if not employee_blocks:
        raise WorkCardPayloadError("Απαιτείται τουλάχιστον ένας εργαζόμενος")
    aa = str(branch_aa or "0").strip()[:5] or "0"
    dates = [str(block.get("f_date") or "").strip() for block in employee_blocks if block.get("f_date")]
    from_date = min(dates) if dates else " "
    to_date = max(dates) if dates else " "
    return {
        "WTOS": {
            "WTO": [
                {
                    "f_aa_pararthmatos": aa,
                    "f_rel_protocol": " ",
                    "f_rel_date": " ",
                    "f_comments": (comments or "").strip() or None,
                    "f_from_date": from_date,
                    "f_to_date": to_date,
                    "Ergazomenoi": {"ErgazomenoiWTO": employee_blocks},
                }
            ]
        }
    }


def build_wtos_envelope(
    *,
    branch_aa: str,
    employee_afm: str,
    employee_last_name: str,
    employee_first_name: str,
    reference_date: str,
    schedule_type: str = "ΕΡΓ",
    hour_from: str | None = None,
    hour_to: str | None = None,
    intervals: list[dict[str, Any]] | None = None,
    comments: str | None = None,
) -> dict[str, Any]:
    employee_block = _employee_wto_daily_block(
        employee_afm=employee_afm,
        employee_last_name=employee_last_name,
        employee_first_name=employee_first_name,
        reference_date=reference_date,
        schedule_type=schedule_type,
        hour_from=hour_from,
        hour_to=hour_to,
        intervals=intervals,
    )
    return _wto_envelope_from_employees(
        branch_aa=branch_aa,
        employee_blocks=[employee_block],
        comments=comments,
    )


def build_wto_daily_a_batch_payload(
    *,
    branch_aa: str,
    employees: list[dict[str, Any]],
    comments: str | None = None,
) -> dict[str, Any]:
    blocks = [
        _employee_wto_daily_block(
            employee_afm=str(item["employee_afm"]),
            employee_last_name=str(item["employee_last_name"]),
            employee_first_name=str(item["employee_first_name"]),
            reference_date=str(item["reference_date"]),
            schedule_type=str(item.get("schedule_type") or "ΕΡΓ"),
            hour_from=item.get("hour_from"),
            hour_to=item.get("hour_to"),
            intervals=item.get("intervals") if isinstance(item.get("intervals"), list) else None,
        )
        for item in employees
    ]
    return _wto_envelope_from_employees(branch_aa=branch_aa, employee_blocks=blocks, comments=comments)


def build_wto_daily_payload(**kwargs: Any) -> dict[str, Any]:
    return build_wtos_envelope(**kwargs)


def build_wto_daily_a_payload(**kwargs: Any) -> dict[str, Any]:
    return build_wtos_envelope(**kwargs)


__all__ = [
    "SUBMISSION_CODE_WTO_DAILY",
    "SUBMISSION_CODE_WTO_DAILY_A",
    "build_wtos_envelope",
    "build_wto_daily_payload",
    "build_wto_daily_a_payload",
    "build_wto_daily_a_batch_payload",
]
