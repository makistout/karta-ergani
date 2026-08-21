"""Pure payroll timekeeping calculations over finalized retrospective rows."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta
import re
from typing import Any, Iterable


ANNUAL_OVERTIME_LIMIT_MINUTES = 150 * 60
_SLOT_RE = re.compile(r"(\d{1,2}:\d{2})\s*[–-]\s*(\d{1,2}:\d{2})")
PREMIUM_KEYS = ("day", "night", "sunday_holiday", "night_sunday_holiday")


def _hm_minutes(value: str) -> int:
    hour, minute = (int(part) for part in value.split(":", 1))
    if hour > 23 or minute > 59:
        raise ValueError(f"Μη έγκυρη ώρα: {value}")
    return hour * 60 + minute


def _work_date(value: str) -> date:
    for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(str(value)[:10], fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Μη έγκυρη ημερομηνία: {value}")


def parse_intervals(label: str | None, work_date: str) -> list[tuple[datetime, datetime]]:
    """Parse one or more HH:MM-HH:MM slots onto an absolute timeline."""
    anchor = datetime.combine(_work_date(work_date), datetime.min.time())
    result: list[tuple[datetime, datetime]] = []
    previous_end: datetime | None = None
    for start_raw, end_raw in _SLOT_RE.findall(str(label or "")):
        start = anchor + timedelta(minutes=_hm_minutes(start_raw))
        while previous_end is not None and start < previous_end:
            start += timedelta(days=1)
        end = anchor + timedelta(minutes=_hm_minutes(end_raw))
        while end <= start:
            end += timedelta(days=1)
        result.append((start, end))
        previous_end = end
    return result


def _minute_category(moment: datetime, holidays: set[date]) -> str:
    special_day = moment.weekday() == 6 or moment.date() in holidays
    night = moment.hour >= 22 or moment.hour < 6
    if special_day and night:
        return "night_sunday_holiday"
    if special_day:
        return "sunday_holiday"
    if night:
        return "night"
    return "day"


def _allocate_contiguous_break(
    minutes: list[datetime], break_minutes: int, holidays: set[date]
) -> set[datetime]:
    """Place one contiguous break at the earliest eligible internal point."""
    duration = max(0, int(break_minutes or 0))
    if duration == 0 or len(minutes) <= duration + 1:
        return set()

    # Never at the first or last minute of the recognized base.
    starts = range(1, len(minutes) - duration)
    for premium_free in (True, False):
        for index in starts:
            window = minutes[index:index + duration]
            if len(window) != duration:
                continue
            if any(window[pos] + timedelta(minutes=1) != window[pos + 1]
                   for pos in range(len(window) - 1)):
                continue
            if premium_free and any(_minute_category(item, holidays) != "day" for item in window):
                continue
            return set(window)
    return set()


def _row_basis_label(row: dict[str, Any]) -> tuple[str, str]:
    status = str(row.get("status") or "").strip().lower()
    if status == "review":
        raise ValueError("Η ωρομέτρηση δεν επιτρέπεται όσο υπάρχουν εγγραφές για έλεγχο")
    if status == "change":
        return str(row.get("proposed") or row.get("declared") or ""), "effective_proposed"
    source = "declared_no_punch" if int(row.get("punch_count") or 0) == 0 else "declared_compliant"
    return str(row.get("declared") or ""), source


def _interval_minutes(intervals: Iterable[tuple[datetime, datetime]]) -> list[datetime]:
    result: list[datetime] = []
    for start, end in intervals:
        cursor = start
        while cursor < end:
            result.append(cursor)
            cursor += timedelta(minutes=1)
    return result


def _empty_breakdown() -> dict[str, int]:
    return {key: 0 for key in PREMIUM_KEYS}


def _categorize_timeline(timeline: Iterable[datetime], holidays: set[date]) -> dict[str, int]:
    result = _empty_breakdown()
    for moment in timeline:
        result[_minute_category(moment, holidays)] += 1
    return result


def _breakdown_total(value: dict[str, int] | None) -> int:
    return sum(int((value or {}).get(key) or 0) for key in PREMIUM_KEYS)


def _apply_exclusive_base_allocation(day: dict[str, Any]) -> None:
    """Remove specially classified base minutes from the ordinary base buckets."""
    ordinary = dict(day.get("premium_minutes") or _empty_breakdown())
    special_fields = (
        "sixth_day_breakdown", "partial_additional_12_breakdown",
        "_partial_overtime_120_breakdown",
    )
    for field in special_fields:
        for key in PREMIUM_KEYS:
            ordinary[key] = max(0, int(ordinary.get(key) or 0) - int((day.get(field) or {}).get(key) or 0))
    day["premium_minutes"] = ordinary
    allocated = _breakdown_total(ordinary) + sum(
        _breakdown_total(day.get(field)) for field in special_fields
    )
    day["base_allocation_integrity_minutes"] = allocated
    base_allocated = allocated - _breakdown_total(day.get("_partial_overtime_120_breakdown"))
    day["partial_base_integrity_minutes"] = base_allocated
    expected_base = int(day.get("recognized_work_minutes") or 0) - int(
        day.get("partial_overtime_120_minutes") or 0
    )
    if allocated != int(day.get("recognized_work_minutes") or 0):
        day["warnings"].append(
            "Ασυμφωνία κατανομής χρόνου: βάση + 6η ημέρα + πρόσθετη μερικής + υπερωρία 120% δεν ισούνται με τον αναγνωρισμένο χρόνο"
        )
    if base_allocated != expected_base:
        day["warnings"].append(
            "Ασυμφωνία βάσης μερικής: κοινή βάση + πρόσθετη μερικής δεν ισούνται με τη βάση έως το ημερήσιο όριο"
        )


def _overtime_timeline(source: dict[str, Any], work_date: str) -> list[datetime]:
    timeline: list[datetime] = []
    for segment in source.get("overtime_segments") or []:
        segment_date = str(segment.get("date") or work_date)
        label = f"{segment.get('from') or ''}–{segment.get('to') or ''}"
        timeline.extend(_interval_minutes(parse_intervals(label, segment_date)))
    if not timeline and source.get("overtime_from") and source.get("overtime_to"):
        label = f"{source.get('overtime_from')}–{source.get('overtime_to')}"
        timeline.extend(_interval_minutes(parse_intervals(label, work_date)))
    return sorted(set(timeline))


def _overwork_timeline(
    source: dict[str, Any], day: dict[str, Any], overtime_timeline: list[datetime],
) -> list[datetime]:
    minutes = max(0, int(day.get("overwork_minutes") or 0))
    if not minutes:
        return []
    if overtime_timeline:
        end = overtime_timeline[0]
    else:
        recognized = day.get("_recognized_timeline") or []
        if recognized:
            end = recognized[-1] + timedelta(minutes=1 + minutes)
        else:
            anchor = datetime.combine(_work_date(day["work_date"]), datetime.min.time())
            actual_start = source.get("actual_start_minutes")
            base = source.get("daily_overtime_basis_minutes")
            if actual_start is None or base is None:
                return []
            end = anchor + timedelta(
                minutes=int(actual_start) + int(source.get("outside_break_minutes") or 0)
                + int(base) + minutes
            )
    start = end - timedelta(minutes=minutes)
    return [start + timedelta(minutes=index) for index in range(minutes)]


def is_timekeeping_leave_row(row: dict[str, Any]) -> bool:
    status = str(row.get("status") or "").strip().lower()
    if status == "change" and str(row.get("proposed") or "").strip():
        values = (row.get("proposed"),)
    else:
        values = (row.get("day_state"), row.get("declared"))
    return any("ΑΔΕΙΑ" in str(value or "").strip().upper() for value in values)


def _display_interval(start: datetime, end: datetime) -> str:
    suffix = " (+1)" if end.date() > start.date() else ""
    return f"{start:%H:%M}–{end:%H:%M}{suffix}"


def _tail_interval_labels(
    timeline: list[datetime], minutes: int, *, tail_offset: int = 0,
) -> list[str]:
    """Return contiguous labels selected backwards from the recognized end."""
    end = max(0, len(timeline) - max(0, int(tail_offset or 0)))
    start = max(0, end - max(0, int(minutes or 0)))
    selected = timeline[start:end]
    if not selected:
        return []
    groups: list[tuple[datetime, datetime]] = []
    group_start = previous = selected[0]
    for moment in selected[1:]:
        if moment != previous + timedelta(minutes=1):
            groups.append((group_start, previous + timedelta(minutes=1)))
            group_start = moment
        previous = moment
    groups.append((group_start, previous + timedelta(minutes=1)))
    return [_display_interval(group_start, group_end) for group_start, group_end in groups]


def _tail_timeline(
    timeline: list[datetime], minutes: int, *, tail_offset: int = 0,
) -> list[datetime]:
    end = max(0, len(timeline) - max(0, int(tail_offset or 0)))
    start = max(0, end - max(0, int(minutes or 0)))
    return timeline[start:end]


def _assign_partial_overtime_120(item: dict[str, Any], minutes: int) -> None:
    """Move the part-time tail above 8:00/6:40 into the common overtime 120% family."""
    amount = max(0, int(minutes or 0))
    timeline = item.get("_recognized_timeline") or []
    selected = _tail_timeline(timeline, amount)
    breakdown = _categorize_timeline(selected, item.get("_premium_holidays") or set())
    item["partial_overtime_120_minutes"] = amount
    item["_partial_overtime_120_breakdown"] = breakdown
    item["overtime_120"] = int(item.get("overtime_120") or 0) + amount
    item["overtime_minutes"] = int(item.get("overtime_minutes") or 0) + amount
    target = item.setdefault("overtime_120_breakdown", _empty_breakdown())
    for key in PREMIUM_KEYS:
        target[key] = int(target.get(key) or 0) + int(breakdown.get(key) or 0)
    item["overtime_120_intervals"] = _tail_interval_labels(timeline, amount)


def build_recognized_day(
    row: dict[str, Any], holidays: set[date], *, sunday_work_enabled: bool,
) -> dict[str, Any]:
    label, basis_source = _row_basis_label(row)
    intervals = parse_intervals(label, str(row.get("work_date") or ""))
    outside_break = max(0, int(row.get("outside_break_minutes") or 0))
    if intervals and outside_break:
        start, end = intervals[-1]
        intervals[-1] = (start, end + timedelta(minutes=outside_break))
    physical_minutes = _interval_minutes(intervals)
    break_duration = max(0, int(row.get("break_minutes") or 0))
    # Sundays always use the recognized basis.  On an official holiday, a store
    # without Sunday operation creates premiums only when a punch exists.
    premium_holidays = holidays if sunday_work_enabled or int(row.get("punch_count") or 0) > 0 else set()
    break_set = _allocate_contiguous_break(physical_minutes, break_duration, premium_holidays)
    recognized_timeline = [minute for minute in physical_minutes if minute not in break_set]
    categories = _categorize_timeline(recognized_timeline, premium_holidays)

    break_label = None
    if break_set:
        ordered = sorted(break_set)
        break_label = _display_interval(ordered[0], ordered[-1] + timedelta(minutes=1))
    warnings: list[str] = []
    if break_duration and physical_minutes and not break_set:
        warnings.append("Δεν βρέθηκε εσωτερικό συνεχόμενο διάστημα που να χωρά ολόκληρο το διάλειμμα")

    return {
        "employee_afm": str(row.get("employee_afm") or ""),
        "eponymo": row.get("eponymo") or "",
        "onoma": row.get("onoma") or "",
        "work_date": str(row.get("work_date") or ""),
        "status": row.get("status"),
        "basis_source": basis_source,
        "basis_label": " · ".join(_display_interval(start, end) for start, end in intervals),
        "recognized_span_minutes": len(physical_minutes),
        "break_minutes": len(break_set),
        "break_interval": break_label,
        "recognized_work_minutes": len(physical_minutes) - len(break_set),
        "premium_minutes": categories,
        "_premium_holidays": premium_holidays,
        "warnings": warnings,
        "contract_kind": row.get("contract_kind"),
        "weekly_days": row.get("weekly_days"),
        "contract_weekly_minutes": row.get("contract_weekly_minutes"),
        "special_arrangement": bool(row.get("work_arrangement") or row.get("uneven_distribution")),
        # Keep the approved retrospective facts on the common calculation row.
        # Exporters are projections of this report and must never recalculate rules.
        "declared": row.get("declared") or "",
        "proposed": row.get("proposed") or "",
        # For payroll purposes an approved change replaces the original
        # declaration.  The original value above remains available only for
        # retrospective/audit use.
        "effective_declared": label,
        "actual": row.get("actual") or "",
        "punch_recorded": row.get("punch_recorded") or "",
        "actual_minutes": row.get("actual_minutes"),
        "day_state": row.get("day_state") or "",
        "overwork_minutes": int(row.get("overwork_minutes") or 0),
        "unlawful_overtime_minutes": int(row.get("unlawful_overtime_minutes") or 0),
        "_recognized_timeline": recognized_timeline,
    }


def _split_overtime(
    *, minutes: int, prior_annual_minutes: int, daily_prior_minutes: int
) -> tuple[dict[str, int], int, int]:
    """Split chronologically: first four daily hours 40/60, remainder 120%."""
    result = {"overtime_40": 0, "overtime_60": 0, "overtime_120": 0}
    remaining = max(0, int(minutes))
    daily_legal_room = max(0, 4 * 60 - daily_prior_minutes)
    legal = min(remaining, daily_legal_room)
    below_annual = max(0, ANNUAL_OVERTIME_LIMIT_MINUTES - prior_annual_minutes)
    at_40 = min(legal, below_annual)
    result["overtime_40"] = at_40
    result["overtime_60"] = legal - at_40
    result["overtime_120"] = remaining - legal
    return result, prior_annual_minutes + legal, daily_prior_minutes + legal


def build_timekeeping_report(
    rows: list[dict[str, Any]], *, holidays: set[date] | None = None,
    annual_context_by_employee: dict[str, dict[str, Any]] | None = None,
    sunday_work_enabled: bool = False,
    next_week_context_by_employee: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build a deterministic preview from finalized apologistic rows."""
    holiday_dates = set(holidays or set())
    contexts = annual_context_by_employee or {}
    payroll_rows = [row for row in rows if not is_timekeeping_leave_row(row)]
    if any(str(row.get("status") or "").lower() == "review" for row in payroll_rows):
        raise ValueError("Υπάρχουν εγγραφές για έλεγχο. Ολοκληρώστε πρώτα το απολογιστικό.")

    days = [
        build_recognized_day(row, holiday_dates, sunday_work_enabled=sunday_work_enabled)
        for row in payroll_rows
    ]
    source_by_key = {
        (str(row.get("employee_afm") or ""), str(row.get("work_date") or "")): row
        for row in payroll_rows
    }
    running = {
        afm: int(context.get("legal_overtime_minutes_before_period") or 0)
        for afm, context in contexts.items()
    }
    daily_overtime: dict[tuple[str, str], int] = defaultdict(int)
    for day in sorted(days, key=lambda item: (_work_date(item["work_date"]), item["employee_afm"])):
        key = (day["employee_afm"], day["work_date"])
        source = source_by_key[key]
        overtime = max(0, int(source.get("overtime_minutes") or 0))
        if str(day.get("contract_kind") or "") == "Μερική":
            overtime = 0
        if day["special_arrangement"]:
            day["warnings"].append(
                "Ειδικό καθεστώς διευθέτησης/ανισομερούς κατανομής: δεν έγινε τελικός χαρακτηρισμός υπερωρίας"
            )
            overtime = 0
        split, annual_after, daily_after = _split_overtime(
            minutes=overtime,
            prior_annual_minutes=running.get(day["employee_afm"], 0),
            daily_prior_minutes=daily_overtime[key],
        )
        running[day["employee_afm"]] = annual_after
        daily_overtime[key] = daily_after
        day.update(split)
        day["overtime_minutes"] = overtime
        overtime_timeline = _overtime_timeline(source, day["work_date"])
        if len(overtime_timeline) > overtime:
            overtime_timeline = overtime_timeline[:overtime]
        if overtime and len(overtime_timeline) < overtime:
            day["warnings"].append(
                "Δεν βρέθηκε πλήρες χρονικό διάστημα για τον επιμερισμό της υπερωρίας σε προσαυξήσεις"
            )
        position = 0
        for field in ("overtime_40", "overtime_60", "overtime_120"):
            field_minutes = int(day.get(field) or 0)
            selected = overtime_timeline[position:position + field_minutes]
            day[f"{field}_breakdown"] = _categorize_timeline(selected, holiday_dates)
            position += field_minutes
        overwork_timeline = _overwork_timeline(source, day, overtime_timeline)
        day["overwork_breakdown"] = _categorize_timeline(overwork_timeline, holiday_dates)
        if day["overwork_minutes"] and len(overwork_timeline) < day["overwork_minutes"]:
            day["warnings"].append(
                "Δεν βρέθηκε πλήρες χρονικό διάστημα για τον επιμερισμό της υπερεργασίας σε προσαυξήσεις"
            )
        context = contexts.get(day["employee_afm"], {})
        if context and not context.get("data_complete", True):
            day["warnings"].append("Το ετήσιο ιστορικό υπερωριών δεν είναι πλήρες")

    by_employee_days: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for day in days:
        by_employee_days[day["employee_afm"]].append(day)
    next_week_contexts = next_week_context_by_employee or {}
    sixth_day_priority = {6: 0, 5: 1, 4: 2, 3: 3, 2: 4, 1: 5, 0: 6}
    for employee_afm, employee_days in by_employee_days.items():
        employee_days.sort(key=lambda item: _work_date(item["work_date"]))
        working_days = [item for item in employee_days if item["recognized_work_minutes"] > 0]

        # Full-time sixth-day rule. Candidates are the shortest recognized
        # bases; ties run Sunday backwards to Monday. Seven days allow at most
        # two candidates, six days at most one.
        for item in employee_days:
            item["sixth_day_minutes"] = 0
            item["sixth_day_breakdown"] = _empty_breakdown()
        contract_kind = str(working_days[0].get("contract_kind") or "") if working_days else ""
        candidates: list[dict[str, Any]] = []
        remaining = list(working_days)
        if contract_kind == "Πλήρης" and len(remaining) == 7:
            first = min(
                remaining,
                key=lambda item: (item["recognized_work_minutes"], sixth_day_priority[_work_date(item["work_date"]).weekday()]),
            )
            candidates.append(first)
            remaining.remove(first)
            if sum(item["recognized_work_minutes"] for item in remaining) > 2400:
                candidates.append(min(
                    remaining,
                    key=lambda item: (item["recognized_work_minutes"], sixth_day_priority[_work_date(item["work_date"]).weekday()]),
                ))
        elif contract_kind == "Πλήρης" and len(remaining) == 6 \
                and sum(item["recognized_work_minutes"] for item in remaining) > 2400:
            candidates.append(min(
                remaining,
                key=lambda item: (item["recognized_work_minutes"], sixth_day_priority[_work_date(item["work_date"]).weekday()]),
            ))

        sunday = next((item for item in working_days if _work_date(item["work_date"]).weekday() == 6), None)
        next_context = next_week_contexts.get(employee_afm, {})
        exemption = (
            not sunday_work_enabled
            and sunday is not None
            and int(sunday["recognized_work_minutes"] or 0) > 5 * 60
            and bool(next_context.get("known"))
            and int(next_context.get("explicit_rest_days") or 0) >= 3
        )
        for candidate in candidates:
            if exemption:
                candidate["warnings"].append(
                    "Δεν χρεώθηκε ως 6η ημέρα: Κυριακή άνω των 5 ωρών και τουλάχιστον 3 ρητά ρεπό στην επόμενη εβδομάδα"
                )
                continue
            candidate["sixth_day_minutes"] = candidate["recognized_work_minutes"]
            candidate["sixth_day_breakdown"] = dict(candidate["premium_minutes"])

        # Weekly allocator for part-time work. The weekly excess is authoritative;
        # daily excess alone never creates the 12% category.
        for item in employee_days:
            item["partial_additional_12"] = 0
            item["partial_overtime_120_minutes"] = 0
            item["partial_additional_12_intervals"] = []
            item["overtime_120_intervals"] = []
            item["partial_additional_12_breakdown"] = _empty_breakdown()
            item["_partial_overtime_120_breakdown"] = _empty_breakdown()
        if working_days and str(working_days[0].get("contract_kind") or "") == "Μερική":
            contract_weekly = working_days[0].get("contract_weekly_minutes")
            weekly_days = int(working_days[0].get("weekly_days") or 0)
            if contract_weekly is None or weekly_days <= 0:
                for item in working_days:
                    item["warnings"].append("Λείπουν συμβατικές εβδομαδιαίες ώρες για την πρόσθετη εργασία μερικής")
            else:
                excess = max(0, sum(item["recognized_work_minutes"] for item in working_days) - int(contract_weekly))
                daily_imputed = int(contract_weekly) // weekly_days
                full_day_cap = 480 if weekly_days == 5 else 400 if weekly_days == 6 else None
                for item in working_days:
                    if full_day_cap is not None:
                        _assign_partial_overtime_120(
                            item, max(0, item["recognized_work_minutes"] - full_day_cap)
                        )
                remaining_excess = max(
                    0, excess - sum(item["partial_overtime_120_minutes"] for item in working_days)
                )
                # The labour-law allocation order is Sunday backwards to Monday.
                for item in reversed(working_days):
                    eligible = max(0, min(item["recognized_work_minutes"], full_day_cap or 10**9) - daily_imputed)
                    allocated = min(remaining_excess, eligible)
                    item["partial_additional_12"] = allocated
                    remaining_excess -= allocated
                if remaining_excess:
                    for item in reversed(working_days):
                        room = max(0, item["recognized_work_minutes"] - item["partial_overtime_120_minutes"] - item["partial_additional_12"])
                        allocated = min(remaining_excess, room)
                        item["partial_additional_12"] += allocated
                        remaining_excess -= allocated
                        if not remaining_excess:
                            break

                # Placement is always at the recognized end, counting backwards.
                # The overtime 120% tail is outside the part-time base; the 12% band ends before it.
                for item in working_days:
                    timeline = item.get("_recognized_timeline") or []
                    item["partial_additional_12_intervals"] = _tail_interval_labels(
                        timeline, item["partial_additional_12"],
                        tail_offset=item["partial_overtime_120_minutes"],
                    )
                    item["partial_additional_12_breakdown"] = _categorize_timeline(
                        _tail_timeline(
                            timeline, item["partial_additional_12"],
                            tail_offset=item["partial_overtime_120_minutes"],
                        ),
                        item.get("_premium_holidays") or set(),
                    )

        # Rotating employment: every recognized day beyond the contractual
        # weekly day count is an extra-part-time day. Selection runs from
        # Sunday backwards to Monday and may yield more than one day.
        if working_days and str(working_days[0].get("contract_kind") or "") == "Εκ περιτροπής":
            contractual_days = int(working_days[0].get("weekly_days") or 0)
            extra_count = max(0, len(working_days) - contractual_days) if contractual_days > 0 else 0
            full_day_cap = 480 if contractual_days == 5 else 400 if contractual_days == 6 else None
            for item in reversed(working_days):
                if extra_count <= 0:
                    break
                timeline = item.get("_recognized_timeline") or []
                item["rotation_extra_day"] = True
                _assign_partial_overtime_120(
                    item,
                    max(0, item["recognized_work_minutes"] - full_day_cap)
                    if full_day_cap is not None else 0,
                )
                item["partial_additional_12"] = max(
                    0, item["recognized_work_minutes"] - item["partial_overtime_120_minutes"]
                )
                item["partial_additional_12_intervals"] = _tail_interval_labels(
                    timeline, item["partial_additional_12"],
                    tail_offset=item["partial_overtime_120_minutes"],
                )
                premium_holidays = item.get("_premium_holidays") or set()
                item["partial_additional_12_breakdown"] = _categorize_timeline(
                    _tail_timeline(
                        timeline, item["partial_additional_12"],
                        tail_offset=item["partial_overtime_120_minutes"],
                    ),
                    premium_holidays,
                )
                extra_count -= 1

        for item in employee_days:
            item.setdefault("rotation_extra_day", False)
            _apply_exclusive_base_allocation(item)

    employee_totals: dict[str, dict[str, Any]] = {}
    for day in days:
        afm = day["employee_afm"]
        total = employee_totals.setdefault(afm, {
            "employee_afm": afm, "eponymo": day["eponymo"], "onoma": day["onoma"],
            "recognized_work_minutes": 0, "day": 0, "night": 0,
            "sunday_holiday": 0, "night_sunday_holiday": 0,
            "overtime_40": 0, "overtime_60": 0, "overtime_120": 0,
            "partial_additional_12": 0, "sixth_day_minutes": 0,
        })
        total["recognized_work_minutes"] += day["recognized_work_minutes"]
        for key, value in day["premium_minutes"].items():
            total[key] += value
        for key in ("overtime_40", "overtime_60", "overtime_120"):
            total[key] += day[key]
        for key in ("partial_additional_12", "sixth_day_minutes"):
            total[key] += day[key]
        for family in (
            "overwork", "overtime_40", "overtime_60", "overtime_120",
            "partial_additional_12", "sixth_day",
        ):
            target = total.setdefault(f"{family}_breakdown", _empty_breakdown())
            for category, value in (day.get(f"{family}_breakdown") or {}).items():
                target[category] += int(value or 0)
    for afm, total in employee_totals.items():
        total["annual_legal_overtime_minutes_after_period"] = running.get(afm, 0)

    for day in days:
        day.pop("_recognized_timeline", None)
        day.pop("_premium_holidays", None)
        day.pop("_partial_overtime_120_breakdown", None)

    return {
        "calculation_version": "timekeeping-v5-partial-overtime-120",
        "days": days,
        "employees": sorted(employee_totals.values(), key=lambda item: (item["eponymo"], item["onoma"], item["employee_afm"])),
        "counts": {"days": len(days), "employees": len(employee_totals)},
    }
