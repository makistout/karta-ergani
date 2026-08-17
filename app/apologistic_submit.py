"""Μετατροπή γραμμών απολογιστικού σε σώματα υποβολής Ergani."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from app.work_card_payload import WorkCardPayloadError

_PROPOSED_RANGE = re.compile(
    r"^([01]\d|2[0-3]):[0-5]\d[–-]([01]\d|2[0-3]):[0-5]\d$"
)
_REST_LABELS = frozenset({"ΑΝΑΠΑΥΣΗ/ΡΕΠΟ", "ΡΕΠΟ", "ΑΝΑΠΑΥΣΗ", "ΑΝ"})
_NON_WORK_LABELS = frozenset({"ΜΗ ΕΡΓΑΣΙΑ", "ΜΕ"})
_TELEWORK_RANGE = re.compile(
    r"^(?:ΤΗΛΕΡΓΑΣΙΑ|ΤΗΛ)((?:[01]\d|2[0-3]):[0-5]\d)[–-]((?:[01]\d|2[0-3]):[0-5]\d)$",
    re.IGNORECASE,
)


def parse_proposed_schedule(value: str) -> tuple[str | None, str | None, str]:
    label = str(value or "").strip()
    upper = label.upper()
    compact = re.sub(r"\s+", "", label)
    if not label:
        return None, None, "ΑΝ"
    if upper in _NON_WORK_LABELS or upper.startswith("ΜΗ ΕΡΓΑΣΙΑ"):
        return None, None, "ΜΕ"
    if upper in _REST_LABELS or "ΡΕΠΟ" in upper or "ΑΝΑΠΑΥΣ" in upper:
        return None, None, "ΑΝ"
    tele = _TELEWORK_RANGE.match(compact)
    if tele:
        return tele.group(1), tele.group(2), "ΤΗΛ"
    if upper.startswith("ΤΗΛΕΡΓΑΣ") or upper.startswith("ΤΗΛ"):
        raise WorkCardPayloadError(f"Η τηλεργασία απαιτεί ωράριο ΩΩ:ΛΛ–ΩΩ:ΛΛ: {value}")
    match = _PROPOSED_RANGE.match(compact)
    if not match:
        raise WorkCardPayloadError(f"Μη έγκυρη πρόταση ωραρίου: {value}")
    parts = re.split(r"[–-]", compact, maxsplit=1)
    return parts[0], parts[1], "ΕΡΓ"


def work_date_to_reference_iso(work_date: str) -> str:
    raw = str(work_date or "").strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw[:10], fmt).date().isoformat()
        except ValueError:
            continue
    raise WorkCardPayloadError(f"Μη έγκυρη ημερομηνία: {work_date}")


def ergani_date_to_work_date(value: str) -> str | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(raw[:10], fmt).date().strftime("%d/%m/%Y")
        except ValueError:
            continue
    return None


def parse_wto_request_meta(request_json: str | None) -> tuple[str | None, str | None, str | None]:
    """Εξαγωγή ΑΦΜ, ημερομηνίας (dd/mm/yyyy) και προτεινόμενου ωραρίου από request_json."""
    if not request_json:
        return None, None, None
    try:
        import json

        data = json.loads(request_json)
    except (TypeError, ValueError):
        return None, None, None
    wto_list = (data.get("WTOS") or {}).get("WTO") if isinstance(data, dict) else None
    if not isinstance(wto_list, list) or not wto_list:
        return None, None, None
    wto = wto_list[0] if isinstance(wto_list[0], dict) else {}
    employees = (wto.get("Ergazomenoi") or {}).get("ErgazomenoiWTO")
    if not isinstance(employees, list) or not employees:
        return None, None, None
    emp = employees[0] if isinstance(employees[0], dict) else {}
    afm = str(emp.get("f_afm") or "").strip() or None
    work_date = ergani_date_to_work_date(str(emp.get("f_date") or wto.get("f_from_date") or ""))
    proposed = None
    analytics = (emp.get("ErgazomenosAnalytics") or {}).get("ErgazomenosWTOAnalytics")
    if isinstance(analytics, list) and analytics:
        first = analytics[0] if isinstance(analytics[0], dict) else {}
        hf = str(first.get("f_from") or "").strip()
        ht = str(first.get("f_to") or "").strip()
        if hf and ht and hf not in {" ", "-"} and ht not in {" ", "-"}:
            proposed = f"{hf}–{ht}"
    return afm, work_date, proposed


def load_apologistic_day_row(
    *,
    store_id: int,
    week_from,
    employee_afm: str,
    work_date,
) -> dict[str, Any]:
    from app.repo_apologistic import load_report

    loaded = load_report(store_id, week_from)
    if not loaded:
        raise LookupError("Δεν βρέθηκε αποθηκευμένο απολογιστικό για αυτή την εβδομάδα")
    report, _snapshot = loaded
    target_date = work_date.strftime("%d/%m/%Y")
    for row in report.get("days") or []:
        if str(row.get("employee_afm") or "").strip() != employee_afm:
            continue
        if str(row.get("work_date") or "").strip() != target_date:
            continue
        return row
    raise LookupError("Δεν βρέθηκε η ημερήσια γραμμή στο απολογιστικό")


def row_has_overtime(row: dict[str, Any]) -> bool:
    segments = row.get("overtime_segments")
    if isinstance(segments, list) and segments:
        return True
    return int(row.get("overtime_minutes") or 0) > 0


def schedule_body_from_apologistic_row(row: dict[str, Any]) -> dict[str, Any]:
    status = str(row.get("status") or row.get("result") or "").strip()
    if status != "change":
        raise WorkCardPayloadError("Η γραμμή δεν έχει αποτέλεσμα «Μεταβολή»")
    proposed = str(row.get("proposed") or "").strip()
    declared = str(row.get("declared") or "").strip()
    if declared and proposed == declared and row_has_overtime(row):
        raise WorkCardPayloadError(
            "Η πρόταση ωραρίου συμπίπτει με το δηλωμένο· απαιτείται μόνο απολογιστική υπερωρία"
        )
    slot_labels = [part.strip() for part in proposed.split(" · ") if part.strip()]
    intervals = None
    if len(slot_labels) > 1:
        parsed_slots = [parse_proposed_schedule(part) for part in slot_labels]
        if any(item[2] != "ΕΡΓ" for item in parsed_slots):
            raise WorkCardPayloadError("Το σπαστό απολογιστικό πρέπει να περιέχει μόνο διαστήματα εργασίας")
        intervals = [{"hour_from": item[0], "hour_to": item[1]} for item in parsed_slots]
        hour_from = hour_to = None
        schedule_type = "ΕΡΓ"
    else:
        hour_from, hour_to, schedule_type = parse_proposed_schedule(proposed)
    if str(row.get("proposed_schedule_type") or "").strip().upper() == "ΤΗΛ":
        schedule_type = "ΤΗΛ"
    return {
        "employee_afm": str(row.get("employee_afm") or "").strip(),
        "eponymo": str(row.get("eponymo") or "").strip(),
        "onoma": str(row.get("onoma") or "").strip(),
        "reference_date": work_date_to_reference_iso(str(row.get("work_date") or "")),
        "schedule_type": schedule_type,
        "hour_from": hour_from,
        "hour_to": hour_to,
        "intervals": intervals,
        "proposed": proposed,
    }


def overtime_segments_from_row(row: dict[str, Any]) -> list[dict[str, str]]:
    segments: list[dict[str, str]] = []
    raw = row.get("overtime_segments")
    if isinstance(raw, list):
        for item in raw:
            if not isinstance(item, dict):
                continue
            hf = str(item.get("from") or item.get("hour_from") or item.get("f_from") or "").strip()
            ht = str(item.get("to") or item.get("hour_to") or item.get("f_to") or "").strip()
            seg_date = str(item.get("date") or row.get("work_date") or "").strip()
            if hf and ht:
                segments.append(
                    {
                        "hour_from": hf,
                        "hour_to": ht,
                        "reference_date": work_date_to_reference_iso(seg_date),
                        "reference_date_ergani": seg_date,
                    }
                )
    if segments:
        return segments
    hf = str(row.get("overtime_from") or "").strip()
    ht = str(row.get("overtime_to") or "").strip()
    if hf and ht:
        work_date = str(row.get("work_date") or "").strip()
        return [
            {
                "hour_from": hf,
                "hour_to": ht,
                "reference_date": work_date_to_reference_iso(work_date),
                "reference_date_ergani": work_date,
            }
        ]
    minutes = int(row.get("overtime_minutes") or 0)
    if minutes > 0:
        raise WorkCardPayloadError("Υπάρχει υπερωρία χωρίς διακριτό διάστημα από–έως")
    return []


def overtime_submit_group_from_row(
    row: dict[str, Any],
    *,
    segment_date_ergani: str | None = None,
) -> tuple[str, list[dict[str, str]]]:
    if str(row.get("status") or "").strip() == "review":
        raise WorkCardPayloadError("Η γραμμή είναι σε «Έλεγχο» και δεν υποβάλλεται")
    segments = overtime_segments_from_row(row)
    if not segments:
        raise WorkCardPayloadError("Δεν προκύπτει υπερωρία για υποβολή")
    if segment_date_ergani:
        filtered = [
            item for item in segments
            if str(item.get("reference_date_ergani") or "").strip() == str(segment_date_ergani).strip()
        ]
        if not filtered:
            raise WorkCardPayloadError("Δεν βρέθηκε το ζητούμενο διάστημα υπερωρίας")
        segments = filtered
    groups: dict[str, list[dict[str, str]]] = {}
    for item in segments:
        groups.setdefault(str(item["reference_date"]), []).append(item)
    if len(groups) != 1:
        dates = ", ".join(sorted({str(item.get("reference_date_ergani") or "") for item in segments}))
        raise WorkCardPayloadError(
            f"Η υπερωρία απλώνεται σε περισσότερες από μία ημέρες ({dates}). "
            "Υποβάλετε κάθε ημέρα ξεχωριστά με segment_date."
        )
    reference_date = next(iter(groups))
    return reference_date, groups[reference_date]
