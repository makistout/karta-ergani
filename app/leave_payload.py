"""Κατασκευή σώματος POST Documents/WTOLeave."""

from __future__ import annotations

from typing import Any

from app.date_util import format_date_for_ergani
from app.leave_types import LEAVE_TYPES, SUBMISSION_CODE_WTO_LEAVE
from app.work_card_payload import WorkCardPayloadError, norm_afm

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

    return {
        "WTOS": {
            "WTO": [
                {
                    "f_aa_pararthmatos": aa,
                    "f_rel_protocol": " ",
                    "f_rel_date": " ",
                    "f_comments": (comments or "").strip() or None,
                    "f_from_date": ergani_date,
                    "f_to_date": ergani_date,
                    "Ergazomenoi": {"ErgazomenoiWTO": [employee_block]},
                }
            ]
        }
    }


__all__ = ["SUBMISSION_CODE_WTO_LEAVE", "build_wto_leave_payload", "LEAVE_TYPES"]
