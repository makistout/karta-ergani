"""Pure payroll timekeeping calculations over finalized retrospective rows."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta
import re
from typing import Any, Iterable


ANNUAL_OVERTIME_LIMIT_MINUTES = 150 * 60
_SLOT_RE = re.compile(r"(\d{1,2}:\d{2})\s*[–-]\s*(\d{1,2}:\d{2})")


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
    categories: dict[str, int] = defaultdict(int)
    for minute in recognized_timeline:
        categories[_minute_category(minute, premium_holidays)] += 1

    break_label = None
    if break_set:
        ordered = sorted(break_set)
        break_label = _display_interval(ordered[0], ordered[-1] + timedelta(minutes=1))
    warnings: list[str] = []
    if break_duration and not break_set:
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
        "premium_minutes": {
            "day": categories["day"],
            "night": categories["night"],
            "sunday_holiday": categories["sunday_holiday"],
            "night_sunday_holiday": categories["night_sunday_holiday"],
        },
        "warnings": warnings,
        "contract_kind": row.get("contract_kind"),
        "weekly_days": row.get("weekly_days"),
        "contract_weekly_minutes": row.get("contract_weekly_minutes"),
        "special_arrangement": bool(row.get("work_arrangement") or row.get("uneven_distribution")),
        # Keep the approved retrospective facts on the common calculation row.
        # Exporters are projections of this report and must never recalculate rules.
        "declared": row.get("declared") or "",
        "proposed": row.get("proposed") or "",
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
    if any(str(row.get("status") or "").lower() == "review" for row in rows):
        raise ValueError("Υπάρχουν εγγραφές για έλεγχο. Ολοκληρώστε πρώτα το απολογιστικό.")

    days = [
        build_recognized_day(row, holiday_dates, sunday_work_enabled=sunday_work_enabled)
        for row in rows
    ]
    source_by_key = {(str(row.get("employee_afm") or ""), str(row.get("work_date") or "")): row for row in rows}
    running = {
        afm: int(context.get("legal_overtime_minutes_before_period") or 0)
        for afm, context in contexts.items()
    }
    daily_overtime: dict[tuple[str, str], int] = defaultdict(int)
    for day in sorted(days, key=lambda item: (_work_date(item["work_date"]), item["employee_afm"])):
        key = (day["employee_afm"], day["work_date"])
        source = source_by_key[key]
        overtime = max(0, int(source.get("overtime_minutes") or 0))
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
            item["sixth_day_breakdown"] = {
                "day": 0, "night": 0, "sunday_holiday": 0, "night_sunday_holiday": 0,
            }
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
            item["partial_120"] = 0
            item["partial_additional_12_intervals"] = []
            item["partial_120_intervals"] = []
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
                        item["partial_120"] = max(0, item["recognized_work_minutes"] - full_day_cap)
                remaining_excess = max(0, excess - sum(item["partial_120"] for item in working_days))
                # The labour-law allocation order is Sunday backwards to Monday.
                for item in reversed(working_days):
                    eligible = max(0, min(item["recognized_work_minutes"], full_day_cap or 10**9) - daily_imputed)
                    allocated = min(remaining_excess, eligible)
                    item["partial_additional_12"] = allocated
                    remaining_excess -= allocated
                if remaining_excess:
                    for item in reversed(working_days):
                        room = max(0, item["recognized_work_minutes"] - item["partial_120"] - item["partial_additional_12"])
                        allocated = min(remaining_excess, room)
                        item["partial_additional_12"] += allocated
                        remaining_excess -= allocated
                        if not remaining_excess:
                            break

                # Placement is always at the recognized end, counting backwards.
                # The 120% tail is kept separate and the 12% band ends before it.
                for item in working_days:
                    timeline = item.get("_recognized_timeline") or []
                    item["partial_120_intervals"] = _tail_interval_labels(
                        timeline, item["partial_120"],
                    )
                    item["partial_additional_12_intervals"] = _tail_interval_labels(
                        timeline, item["partial_additional_12"],
                        tail_offset=item["partial_120"],
                    )

    employee_totals: dict[str, dict[str, Any]] = {}
    for day in days:
        afm = day["employee_afm"]
        total = employee_totals.setdefault(afm, {
            "employee_afm": afm, "eponymo": day["eponymo"], "onoma": day["onoma"],
            "recognized_work_minutes": 0, "day": 0, "night": 0,
            "sunday_holiday": 0, "night_sunday_holiday": 0,
            "overtime_40": 0, "overtime_60": 0, "overtime_120": 0,
            "partial_additional_12": 0, "partial_120": 0, "sixth_day_minutes": 0,
        })
        total["recognized_work_minutes"] += day["recognized_work_minutes"]
        for key, value in day["premium_minutes"].items():
            total[key] += value
        for key in ("overtime_40", "overtime_60", "overtime_120"):
            total[key] += day[key]
        for key in ("partial_additional_12", "partial_120", "sixth_day_minutes"):
            total[key] += day[key]
    for afm, total in employee_totals.items():
        total["annual_legal_overtime_minutes_after_period"] = running.get(afm, 0)

    for day in days:
        day.pop("_recognized_timeline", None)

    return {
        "calculation_version": "timekeeping-v2-sixth-day",
        "days": days,
        "employees": sorted(employee_totals.values(), key=lambda item: (item["eponymo"], item["onoma"], item["employee_afm"])),
        "counts": {"days": len(days), "employees": len(employee_totals)},
    }
