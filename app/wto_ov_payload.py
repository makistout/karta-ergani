"""Κατασκευή σώματος POST Documents/WTOOvA — απολογιστικές υπερωρίες."""

from __future__ import annotations

from typing import Any

from app.date_util import format_date_for_ergani
from app.work_card_payload import WorkCardPayloadError, norm_afm

SUBMISSION_CODE_WTO_OV_A = "WTOOvA"
_OVERTIME_TYPE = "ΥΠ"


def _blank_field(value: str | None) -> str:
    s = (value or "").strip()
    return s if s else " "


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
    emp = norm_afm(employee_afm)
    ep = (employee_last_name or "").strip()
    on = (employee_first_name or "").strip()
    if not ep or not on:
        raise WorkCardPayloadError("Απαιτούνται επώνυμο και όνομα εργαζομένου")

    ergani_date = format_date_for_ergani(reference_date)
    aa = str(branch_aa or "0").strip()[:5] or "0"

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

    employee_block = {
        "f_afm": emp,
        "f_eponymo": ep,
        "f_onoma": on,
        "f_date": ergani_date,
        "ErgazomenosAnalytics": {"ErgazomenosWTOAnalytics": analytics},
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


__all__ = ["SUBMISSION_CODE_WTO_OV_A", "build_wto_ov_a_payload"]
