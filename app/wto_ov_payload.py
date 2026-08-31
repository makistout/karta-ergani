"""Κατασκευή σώματος POST Documents/WTOOvA — απολογιστικές υπερωρίες."""

from __future__ import annotations

from typing import Any

from app.date_util import format_date_for_ergani
from app.work_card_payload import WorkCardPayloadError, norm_afm
from app.wto_daily_payload import _wto_envelope_from_employees

SUBMISSION_CODE_WTO_OV_A = "WTOOvA"
_OVERTIME_TYPE = "ΥΠ"


def _blank_field(value: str | None) -> str:
    s = (value or "").strip()
    return s if s else " "


def _overtime_analytics(
    *,
    hour_from: str | None = None,
    hour_to: str | None = None,
    intervals: list[dict[str, Any]] | None = None,
) -> list[dict[str, str]]:
    analytics: list[dict[str, str]] = []
    if intervals:
        for item in intervals:
            hf = str((item or {}).get("hour_from") or "").strip()
            ht = str((item or {}).get("hour_to") or "").strip()
            if not hf and not ht:
                continue
            if not hf or not ht:
                raise WorkCardPayloadError("Σε κάθε διάστημα υπερωρίας απαιτούνται ώρα από και έως")
            analytics.append({"f_type": _OVERTIME_TYPE, "f_from": _blank_field(hf), "f_to": _blank_field(ht)})
    if not analytics:
        hf = str(hour_from or "").strip()
        ht = str(hour_to or "").strip()
        if not hf or not ht:
            raise WorkCardPayloadError("Απαιτούνται hour_from και hour_to (ή intervals)")
        analytics = [{"f_type": _OVERTIME_TYPE, "f_from": _blank_field(hf), "f_to": _blank_field(ht)}]
    return analytics


def _employee_wto_ov_block(
    *,
    employee_afm: str,
    employee_last_name: str,
    employee_first_name: str,
    reference_date: str,
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
            "ErgazomenosWTOAnalytics": _overtime_analytics(
                hour_from=hour_from,
                hour_to=hour_to,
                intervals=intervals,
            ),
        },
    }


def build_wto_ov_a_payload(
    *,
    branch_aa: str,
    employee_afm: str,
    employee_last_name: str,
    employee_first_name: str,
    reference_date: str,
    hour_from: str | None = None,
    hour_to: str | None = None,
    intervals: list[dict[str, Any]] | None = None,
    comments: str | None = None,
) -> dict[str, Any]:
    employee_block = _employee_wto_ov_block(
        employee_afm=employee_afm,
        employee_last_name=employee_last_name,
        employee_first_name=employee_first_name,
        reference_date=reference_date,
        hour_from=hour_from,
        hour_to=hour_to,
        intervals=intervals,
    )
    return _wto_envelope_from_employees(
        branch_aa=branch_aa,
        employee_blocks=[employee_block],
        comments=comments,
    )


def build_wto_ov_a_batch_payload(
    *,
    branch_aa: str,
    employees: list[dict[str, Any]],
    comments: str | None = None,
) -> dict[str, Any]:
    blocks = [
        _employee_wto_ov_block(
            employee_afm=str(item["employee_afm"]),
            employee_last_name=str(item["employee_last_name"]),
            employee_first_name=str(item["employee_first_name"]),
            reference_date=str(item["reference_date"]),
            hour_from=item.get("hour_from"),
            hour_to=item.get("hour_to"),
            intervals=item.get("intervals") if isinstance(item.get("intervals"), list) else None,
        )
        for item in employees
    ]
    return _wto_envelope_from_employees(branch_aa=branch_aa, employee_blocks=blocks, comments=comments)


__all__ = ["SUBMISSION_CODE_WTO_OV_A", "build_wto_ov_a_payload", "build_wto_ov_a_batch_payload"]
