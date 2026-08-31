"""Κατασκευή σώματος POST Documents/WTOLeave."""

from __future__ import annotations

from typing import Any

from app.date_util import format_date_for_ergani
from app.leave_types import LEAVE_TYPES, SUBMISSION_CODE_WTO_LEAVE
from app.work_card_payload import WorkCardPayloadError, norm_afm
from app.wto_daily_payload import _wto_envelope_from_employees

_VALID_CODES = {t["code"] for t in LEAVE_TYPES}


def _blank_field(value: str | None) -> str:
    s = (value or "").strip()
    return s if s else " "


def build_wto_leave_payload(
    *,
    branch_aa: str,
    employee_afm: str,
    employee_last_name: str,
    employee_first_name: str,
    reference_date: str,
    leave_type: str,
    comments: str | None = None,
    hour_from: str | None = None,
    hour_to: str | None = None,
) -> dict[str, Any]:
    emp = norm_afm(employee_afm)
    ep = (employee_last_name or "").strip()
    on = (employee_first_name or "").strip()
    if not ep or not on:
        raise WorkCardPayloadError("Απαιτούνται επώνυμο και όνομα εργαζομένου")

    code = str(leave_type or "").strip().upper()
    if code not in _VALID_CODES:
        raise WorkCardPayloadError(
            f"Μη έγκυρος τύπος άδειας: {leave_type}. "
            f"Επιτρεπτοί: {', '.join(sorted(_VALID_CODES))}"
        )

    ergani_date = format_date_for_ergani(reference_date)
    aa = str(branch_aa or "0").strip()[:5] or "0"

    analytic: dict[str, Any] = {
        "f_type": code,
        "f_from": _blank_field(hour_from),
        "f_to": _blank_field(hour_to),
        "f_year": " ",
        "f_req_days": " ",
    }

    employee_block = {
        "f_afm": emp,
        "f_eponymo": ep,
        "f_onoma": on,
        "f_date": ergani_date,
        "ErgazomenosAnalytics": {"ErgazomenosWTOAnalytics": [analytic]},
    }

    return _wto_envelope_from_employees(
        branch_aa=aa,
        employee_blocks=[employee_block],
        comments=comments,
    )


def build_wto_leave_batch_payload(
    *,
    branch_aa: str,
    employees: list[dict[str, Any]],
    comments: str | None = None,
) -> dict[str, Any]:
    blocks: list[dict[str, Any]] = []
    for item in employees:
        emp = norm_afm(str(item["employee_afm"]))
        ep = str(item.get("employee_last_name") or "").strip()
        on = str(item.get("employee_first_name") or "").strip()
        if not ep or not on:
            raise WorkCardPayloadError("Απαιτούνται επώνυμο και όνομα εργαζομένου")
        code = str(item.get("leave_type") or "").strip().upper()
        if code not in _VALID_CODES:
            raise WorkCardPayloadError(f"Μη έγκυρος τύπος άδειας: {item.get('leave_type')}")
        ergani_date = format_date_for_ergani(str(item["reference_date"]))
        blocks.append({
            "f_afm": emp,
            "f_eponymo": ep,
            "f_onoma": on,
            "f_date": ergani_date,
            "ErgazomenosAnalytics": {
                "ErgazomenosWTOAnalytics": [{
                    "f_type": code,
                    "f_from": _blank_field(item.get("hour_from")),
                    "f_to": _blank_field(item.get("hour_to")),
                    "f_year": " ",
                    "f_req_days": " ",
                }],
            },
        })
    return _wto_envelope_from_employees(
        branch_aa=str(branch_aa or "0").strip()[:5] or "0",
        employee_blocks=blocks,
        comments=comments,
    )


__all__ = [
    "SUBMISSION_CODE_WTO_LEAVE",
    "build_wto_leave_payload",
    "build_wto_leave_batch_payload",
    "LEAVE_TYPES",
]
