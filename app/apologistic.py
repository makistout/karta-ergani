"""Weekly retrospective schedule analysis.

The module deliberately separates facts from suggestions.  It never invents a
punch and sends ambiguous/legal-policy cases to manual review.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time, timedelta
from typing import Any


REST_MARKERS = ("ΑΝΑΠΑΥΣ", "ΡΕΠΟ", "ΜΗ ΕΡΓΑΣΙΑ", "ΑΔΕΙΑ", "ΑΡΓΙΑ")


def previous_week(today: date | None = None) -> tuple[date, date]:
    current = today or date.today()
    this_monday = current - timedelta(days=current.weekday())
    return this_monday - timedelta(days=7), this_monday - timedelta(days=1)


def _clock(value: Any) -> time | None:
    raw = str(value or "").strip()[:5]
    try:
        return datetime.strptime(raw, "%H:%M").time()
    except ValueError:
        return None


def _minutes(start: Any, end: Any) -> int | None:
    left, right = _clock(start), _clock(end)
    if not left or not right:
        return None
    a = left.hour * 60 + left.minute
    b = right.hour * 60 + right.minute
    if b < a:
        b += 24 * 60
    return b - a


def _minute_of_day(value: Any, *, after: int | None = None) -> int | None:
    parsed = _clock(value)
    if not parsed:
        return None
    result = parsed.hour * 60 + parsed.minute
    if after is not None and result < after:
        result += 24 * 60
    return result


def _hm(total: int) -> str:
    total %= 24 * 60
    return f"{total // 60:02d}:{total % 60:02d}"


def _night_minutes(start: Any, end: Any) -> int:
    """Minutes overlapping 22:00–06:00, including overnight shifts."""
    a = _minute_of_day(start)
    b = _minute_of_day(end, after=a) if a is not None else None
    if a is None or b is None:
        return 0
    total = 0
    for day_offset in (-1440, 0, 1440):
        night_start, night_end = day_offset + 22 * 60, day_offset + 30 * 60
        total += max(0, min(b, night_end) - max(a, night_start))
    return total


def _is_rest(slots: list[dict[str, Any]]) -> bool:
    if not slots:
        return False
    label = " ".join(str(s.get("shift_type") or "").upper() for s in slots)
    return any(marker in label for marker in REST_MARKERS)


def _working_slots(slots: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [s for s in slots if _clock(s.get("hour_from")) and _clock(s.get("hour_to"))]


def _best_punch(
    punches: list[dict[str, Any]], slots: list[dict[str, Any]]
) -> dict[str, Any] | None:
    complete = [p for p in punches if _clock(p.get("hour_from")) and _clock(p.get("hour_to"))]
    if not complete:
        return punches[0] if punches else None
    declared = _working_slots(slots)
    if not declared:
        return max(complete, key=lambda p: _minutes(p.get("hour_from"), p.get("hour_to")) or 0)

    def score(punch: dict[str, Any]) -> tuple[int, int]:
        p_start = _minute_of_day(punch.get("hour_from")) or 0
        p_end = _minute_of_day(punch.get("hour_to"), after=p_start) or p_start
        distances = []
        for slot in declared:
            s_start = _minute_of_day(slot.get("hour_from")) or 0
            s_end = _minute_of_day(slot.get("hour_to"), after=s_start) or s_start
            distances.append(abs(p_start - s_start) + abs(p_end - s_end))
        return (min(distances), -(p_end - p_start))

    return min(complete, key=score)


def _contract_kind(contract: dict[str, Any] | None) -> tuple[str, int | None]:
    if not contract:
        return "Άγνωστη σύμβαση", None
    text = " ".join(
        str(contract.get(k) or "").upper()
        for k in ("characterization", "regime", "employment_relation")
    )
    days_raw = str(contract.get("weekly_work_days") or "")
    days = next((n for n in (5, 6) if str(n) in days_raw), None)
    if "ΕΚ ΠΕΡΙΤΡΟΠ" in text:
        return "Εκ περιτροπής", days
    if "ΜΕΡΙΚ" in text:
        return "Μερική", days
    if "ΠΛΗΡ" in text:
        return "Πλήρης", days
    return "Μη προσδιορισμένη", days


def build_weekly_report(
    schedule_rows: list[dict[str, Any]],
    work_rows: list[dict[str, Any]],
    contracts: list[dict[str, Any]],
) -> dict[str, Any]:
    schedules: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    punches: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    contract_by_afm = {str(r.get("employee_afm") or "").zfill(9): r for r in contracts}
    names: dict[str, tuple[str, str]] = {}
    for row in schedule_rows:
        afm = str(row.get("employee_afm") or "").zfill(9)
        key = afm, str(row.get("work_date") or "")
        schedules[key].append(row)
        names[afm] = (str(row.get("eponymo") or ""), str(row.get("onoma") or ""))
    for row in work_rows:
        afm = str(row.get("employee_afm") or "").zfill(9)
        key = afm, str(row.get("work_date") or "")
        punches[key].append(row)
        names[afm] = (str(row.get("eponymo") or ""), str(row.get("onoma") or ""))

    daily: list[dict[str, Any]] = []
    employee_totals: dict[str, dict[str, int]] = defaultdict(lambda: {"declared": 0, "actual": 0, "extra": 0})
    for afm, work_date in sorted(set(schedules) | set(punches), key=lambda k: (k[1], names.get(k[0], ("", "")), k[0])):
        slots = schedules.get((afm, work_date), [])
        day_punches = punches.get((afm, work_date), [])
        selected = _best_punch(day_punches, slots)
        contract = contract_by_afm.get(afm)
        contract_kind, weekly_days = _contract_kind(contract)
        work_slots = _working_slots(slots)
        declared_minutes = sum(_minutes(s.get("hour_from"), s.get("hour_to")) or 0 for s in work_slots)
        actual_minutes = _minutes(selected.get("hour_from"), selected.get("hour_to")) if selected else None
        declared_label = " · ".join(
            f"{s.get('hour_from')}–{s.get('hour_to')}" for s in work_slots
        ) or (str(slots[0].get("shift_type") or "") if slots else "—")
        actual_label = (
            f"{selected.get('hour_from') or '—'}–{selected.get('hour_to') or '—'}"
            if selected else "—"
        )
        flex = int((contract or {}).get("flex_arrival_minutes") or (work_slots[0].get("flex_arrival_minutes") if work_slots else 0) or 0)
        raw_break = (contract or {}).get("break_minutes")
        if raw_break is None and work_slots:
            raw_break = work_slots[0].get("break_minutes")
        break_minutes = max(0, int(raw_break or 0))
        break_in_work = (contract or {}).get("break_in_work")
        if break_in_work is None and work_slots:
            break_in_work = work_slots[0].get("break_in_work")
        outside_break = break_minutes if work_slots and selected and int(break_in_work or 0) == 0 else 0
        gross_difference = (actual_minutes - declared_minutes) if actual_minutes is not None else None
        net_difference = (gross_difference - outside_break) if gross_difference is not None else None
        start_difference = end_difference = None
        if selected and work_slots and actual_minutes is not None:
            declared_start = _minute_of_day(work_slots[0].get("hour_from")) or 0
            declared_end = _minute_of_day(work_slots[-1].get("hour_to"), after=declared_start) or 0
            actual_start = _minute_of_day(selected.get("hour_from")) or 0
            actual_end = _minute_of_day(selected.get("hour_to"), after=actual_start) or 0
            start_difference = actual_start - declared_start
            end_difference = actual_end - declared_end

        day_state = "Ρεπό/απουσία" if _is_rest(slots) else ("Εργασία" if work_slots else "Χωρίς δηλωμένο ωράριο")
        punch_complete = bool(selected and _clock(selected.get("hour_from")) and _clock(selected.get("hour_to")))
        punch_completeness = "Πλήρες" if punch_complete else ("Ελλιπές" if selected else "Χωρίς χτύπημα")
        data_source = "Πραγματική απασχόληση" if selected else "Μόνο δηλωμένο ωράριο"
        status, reason, proposed = "ok", "Δεν απαιτείται μεταβολή", declared_label
        if selected and (not _clock(selected.get("hour_from")) or not _clock(selected.get("hour_to"))):
            status, reason, proposed = "review", "Ελλιπές ζεύγος χτυπημάτων", "Έλεγχος"
        elif selected and (not slots or _is_rest(slots)):
            status, reason, proposed = "review", "Χτύπημα χωρίς ωράριο ή σε ρεπό", actual_label
        elif slots and not selected and work_slots:
            status, reason, proposed = "review", "Δηλωμένο ωράριο χωρίς χτύπημα", "Έλεγχος"
        elif selected and work_slots:
            first = work_slots[0]
            ds = _minute_of_day(first.get("hour_from")) or 0
            de = _minute_of_day(work_slots[-1].get("hour_to"), after=ds) or ds
            ps = _minute_of_day(selected.get("hour_from")) or 0
            pe = _minute_of_day(selected.get("hour_to"), after=ps) or ps
            if ds <= ps <= ds + flex and pe <= de + flex:
                reason = "Εντός δηλωμένου ωραρίου/ευέλικτης προσέλευσης"
            elif len(work_slots) > 1:
                status, reason, proposed = "review", "Απόκλιση σε σπαστό ωράριο", "Έλεγχος"
            else:
                status = "change"
                reason = "Απόκλιση πραγματικής από δηλωμένη απασχόληση"
                proposed = f"{_hm(ps)}–{_hm(ps + declared_minutes)}"

        extra = max(0, net_difference or 0)
        requires_confirmation = status != "ok" or contract_kind in ("Άγνωστη σύμβαση", "Μη προσδιορισμένη")
        confidence = "Χαμηλή" if requires_confirmation else ("Μέση" if len(day_punches) > 1 else "Υψηλή")
        overtime_candidate = extra if contract_kind in ("Πλήρης", "Μερική", "Εκ περιτροπής") else 0
        employee_totals[afm]["declared"] += declared_minutes
        employee_totals[afm]["actual"] += actual_minutes or 0
        employee_totals[afm]["extra"] += extra
        daily.append({
            "employee_afm": afm, "eponymo": names.get(afm, ("", ""))[0],
            "onoma": names.get(afm, ("", ""))[1], "work_date": work_date,
            "contract_kind": contract_kind, "weekly_days": weekly_days,
            "declared": declared_label, "actual": actual_label,
            "proposed": proposed, "status": status, "reason": reason,
            "declared_minutes": declared_minutes, "actual_minutes": actual_minutes,
            "extra_minutes": extra, "punch_count": len(day_punches),
            "day_state": day_state, "punch_completeness": punch_completeness,
            "data_source": data_source, "flex_minutes": flex,
            "start_difference_minutes": start_difference,
            "end_difference_minutes": end_difference,
            "gross_difference_minutes": gross_difference,
            "break_minutes": break_minutes, "outside_break_minutes": outside_break,
            "net_difference_minutes": net_difference,
            "night_minutes": _night_minutes(selected.get("hour_from"), selected.get("hour_to")) if selected else 0,
            "overtime_candidate_minutes": overtime_candidate,
            "requires_confirmation": requires_confirmation, "confidence": confidence,
            "sixth_day_candidate": False,
        })

    # A sixth actual workday is only a warning; legality depends on the applicable regime.
    worked_by_employee: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in daily:
        if row["actual_minutes"] and row["actual_minutes"] > 0:
            worked_by_employee[row["employee_afm"]].append(row)
    for afm, worked_days in worked_by_employee.items():
        if worked_days and worked_days[0].get("weekly_days") == 5 and len(worked_days) > 5:
            for row in sorted(worked_days, key=lambda r: datetime.strptime(r["work_date"], "%d/%m/%Y"))[5:]:
                row["sixth_day_candidate"] = True
                row["requires_confirmation"] = True
                row["confidence"] = "Χαμηλή"

    summaries = []
    for afm, totals in employee_totals.items():
        contract_kind, weekly_days = _contract_kind(contract_by_afm.get(afm))
        summaries.append({"employee_afm": afm, "eponymo": names.get(afm, ("", ""))[0],
                          "onoma": names.get(afm, ("", ""))[1], "contract_kind": contract_kind,
                          "weekly_days": weekly_days, **totals})
    summaries.sort(key=lambda r: (r["eponymo"], r["onoma"], r["employee_afm"]))
    return {"days": daily, "employees": summaries,
            "counts": {"all": len(daily), "ok": sum(r["status"] == "ok" for r in daily),
                       "change": sum(r["status"] == "change" for r in daily),
                       "review": sum(r["status"] == "review" for r in daily)}}
