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


def build_wto_daily_payload(
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
    emp = norm_afm(employee_afm)
    ep = (employee_last_name or "").strip()
    on = (employee_first_name or "").strip()
    if not ep or not on:
        raise WorkCardPayloadError("Απαιτούνται επώνυμο και όνομα εργαζομένου")

    stype = str(schedule_type or "ΕΡΓ").strip().upper()
    if stype == "ERG":
        stype = "ΕΡΓ"
    if stype not in _VALID_TYPES:
        raise WorkCardPayloadError(
            f"Μη έγκυρος τύπος ωραρίου: {schedule_type}. "
            f"Επιτρεπτοί: {', '.join(sorted(_VALID_TYPES))}"
        )

    ergani_date = format_date_for_ergani(reference_date)
    aa = str(branch_aa or "0").strip()[:5] or "0"

    if intervals and stype != "ΑΝ":
        analytics = []
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
    else:
        analytics = [{"f_type": stype, "f_from": _blank_field(hour_from), "f_to": _blank_field(hour_to)}]

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


__all__ = ["SUBMISSION_CODE_WTO_DAILY", "build_wto_daily_payload"]
