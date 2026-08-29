"""Weekly retrospective schedule analysis.

Facts, inferred card boundaries and legal suggestions are kept separately.  A
suggestion is never an automatic Ergani submission; ambiguous cases require
explicit approval.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time, timedelta
from typing import Any
import unicodedata

from app.apologistic_rules import (
    RuleDecision,
    allocate_uneven_distribution,
    classify_extra_minutes,
    contract_daily_base_minutes,
    normal_schedule_decision,
    split_schedule_decision,
)


REST_MARKERS = ("ΑΝΑΠΑΥΣ", "ΡΕΠΟ")
NON_WORK_MARKERS = (*REST_MARKERS, "ΜΗ ΕΡΓΑΣΙΑ", "ΑΔΕΙΑ", "ΑΡΓΙΑ")


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


def _minute_of_day(value: Any, *, after: int | None = None) -> int | None:
    parsed = _clock(value)
    if not parsed:
        return None
    result = parsed.hour * 60 + parsed.minute
    if after is not None and result < after:
        result += 1440
    return result


def _minutes(start: Any, end: Any) -> int | None:
    a = _minute_of_day(start)
    b = _minute_of_day(end, after=a) if a is not None else None
    return b - a if a is not None and b is not None else None


def _is_explicit_next_day(punch: dict[str, Any]) -> bool:
    return punch.get("is_end_date_different") in (True, 1, "1", "true", "True")


def _valid_punch_interval(
    punch: dict[str, Any], *, max_inferred_overnight_minutes: int | None,
) -> tuple[int, int] | None:
    """Return a real positive card interval, preserving explicit calendar-day data.

    A smaller exit clock is moved to the next day only when Ergani marks it as
    such or when the resulting overnight span fits the applicable daily limit.
    """
    start = _minute_of_day(punch.get("hour_from"))
    end = _minute_of_day(punch.get("hour_to"))
    if start is None or end is None:
        return None
    if _is_explicit_next_day(punch):
        end += 1440
    elif end < start:
        inferred_end = end + 1440
        if max_inferred_overnight_minutes is None or inferred_end - start > max_inferred_overnight_minutes:
            return None
        end = inferred_end
    if end <= start:
        return None
    return start, end


def _maximum_valid_punch_span(
    punches: list[dict[str, Any]], *, max_inferred_overnight_minutes: int | None,
) -> tuple[int, int, dict[str, Any], dict[str, Any]] | None:
    """Choose the longest valid start→later-end span across all card rows."""
    candidates: list[tuple[int, int, dict[str, Any], dict[str, Any]]] = []
    starts = [(_minute_of_day(p.get("hour_from")), p) for p in punches if _clock(p.get("hour_from"))]
    for actual_start, first_punch in starts:
        if actual_start is None:
            continue
        for last_punch in punches:
            # A second opening without a closing is corrected to a zero-length
            # row, so that opening may still close the overall envelope.
            has_end = bool(_clock(last_punch.get("hour_to")))
            if has_end and _clock(last_punch.get("hour_from")) and _valid_punch_interval(
                last_punch,
                max_inferred_overnight_minutes=max_inferred_overnight_minutes,
            ) is None:
                # An exit that makes its own recorded row invalid cannot be
                # reused to manufacture a different, longer cross-row span.
                continue
            raw_end = last_punch.get("hour_to") if has_end else (
                last_punch.get("hour_from") if _clock(last_punch.get("hour_from")) else None
            )
            end_clock = _minute_of_day(raw_end)
            if end_clock is None:
                continue
            if has_end and _is_explicit_next_day(last_punch):
                actual_end = end_clock + 1440
            elif end_clock > actual_start:
                actual_end = end_clock
            else:
                actual_end = end_clock + 1440
                if (max_inferred_overnight_minutes is None
                        or actual_end - actual_start > max_inferred_overnight_minutes):
                    continue
            if actual_end > actual_start:
                candidates.append((actual_start, actual_end, first_punch, last_punch))
    return max(candidates, key=lambda item: item[1] - item[0]) if candidates else None


def _overtime_interval_before_general_validation(
    punches: list[dict[str, Any]], slots: list[dict[str, Any]], matched: list[dict[str, Any]],
) -> tuple[int | None, int | None]:
    """Preserve the established overtime clock envelope.

    The stricter valid-pair selection belongs to the general card checks.  It
    must not silently redefine the duration used by the existing overtime
    rules.
    """
    declared = _working_slots(slots)
    if not declared:
        complete = [p for p in punches if _minutes(p.get("hour_from"), p.get("hour_to")) is not None]
        if complete:
            selected = max(
                complete,
                key=lambda p: _minutes(p.get("hour_from"), p.get("hour_to")) or 0,
            )
            start = _minute_of_day(selected.get("hour_from"))
            end = _minute_of_day(selected.get("hour_to"), after=start) if start is not None else None
            return start, end
    elif len(declared) == 1 and punches:
        complete = [p for p in punches if _minutes(p.get("hour_from"), p.get("hour_to")) is not None]
        if complete and len(punches) > 1:
            starts = [_minute_of_day(p.get("hour_from")) for p in punches if _clock(p.get("hour_from"))]
            starts = [value for value in starts if value is not None]
            if starts:
                start = min(starts)
                ends = []
                for item in punches:
                    value = item.get("hour_to") if _clock(item.get("hour_to")) else item.get("hour_from")
                    minute = _minute_of_day(value, after=start)
                    if minute is not None:
                        ends.append(minute)
                if ends:
                    return start, max(ends)
        elif complete:
            selected = complete[0]
            start = _minute_of_day(selected.get("hour_from"))
            end = _minute_of_day(selected.get("hour_to"), after=start) if start is not None else None
            return start, end

    first = matched[0] if matched else None
    last = matched[-1] if matched else None
    start = _minute_of_day(first.get("from")) if first else None
    end = _minute_of_day(last.get("to"), after=start) if last and start is not None else None
    return start, end


def _hm(total: int) -> str:
    total %= 1440
    return f"{total // 60:02d}:{total % 60:02d}"


def _format_recorded_boundary(value: Any) -> str:
    return str(value or "").strip()[:5] if _clock(value) else ""


def _format_recorded_punch(punch: dict[str, Any]) -> str:
    """Ώρες όπως καταγράφονται στην κάρτα· κενό όριο = κενή εμφάνιση."""
    start = _format_recorded_boundary(punch.get("hour_from"))
    end = _format_recorded_boundary(punch.get("hour_to"))
    if not start and not end:
        return "—"
    if start and end:
        next_day = _is_explicit_next_day(punch)
        return f"{start}–{end}{'*' if next_day else ''}"
    if start:
        return f"{start}–"
    return f"–{end}"


def _format_recorded_punches(punches: list[dict[str, Any]]) -> str:
    if not punches:
        return "—"
    return "\n".join(_format_recorded_punch(p) for p in punches)


def _minutes_from_work_anchor(
    anchor_date: date,
    item_date: date,
    clock_value: Any,
    *,
    after_abs: int | None = None,
) -> int | None:
    """Absolute minutes from ``anchor_date`` midnight on the work-day timeline."""
    clock_min = _minute_of_day(clock_value)
    if clock_min is None:
        return None
    result = (item_date - anchor_date).days * 1440 + clock_min
    if after_abs is not None and result < after_abs:
        result += 1440
    return result


def _partition_punches_covered_by_previous_overnight(
    punches: dict[tuple[str, str], list[dict[str, Any]]],
    schedules: dict[tuple[str, str], list[dict[str, Any]]],
    contracts_by_afm: dict[str, dict[str, Any]],
    weekly_system_by_afm: dict[str, tuple[int | None, str]],
) -> tuple[
    dict[tuple[str, str], list[dict[str, Any]]],
    dict[tuple[str, str], list[dict[str, Any]]],
]:
    """Move next-calendar-day punches back when they fall within the daily span window.

    Applies when the previous day has one assumed start.  Candidate pairs on the next
    calendar day must fall within assumed_start + contractual daily span (13 h for
    5-day / 12 h for 6-day) plus outside break, and begin before the declared main
    shift of the new day.  Judgment is by clock times only; the ``*`` marker is not
    used as a gate for this rule.
    """
    excluded_from_current: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    attributed_to_previous: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)

    def key_date(key: tuple[str, str]) -> date:
        try:
            return datetime.strptime(key[1], "%d/%m/%Y").date()
        except ValueError:
            return date.max

    def row_end_abs(anchor_date: date, row: dict[str, Any]) -> int | None:
        start_abs = _minutes_from_work_anchor(anchor_date, anchor_date, row.get("hour_from"))
        end_abs = _minutes_from_work_anchor(anchor_date, anchor_date, row.get("hour_to"))
        if start_abs is None or end_abs is None:
            return None
        if _is_explicit_next_day(row):
            end_abs += 1440
        elif end_abs < start_abs:
            end_abs += 1440
        return end_abs

    for key in sorted(list(punches), key=key_date):
        afm, work_date = key
        try:
            current_date = datetime.strptime(work_date, "%d/%m/%Y").date()
        except ValueError:
            continue
        previous_date = current_date - timedelta(days=1)
        previous_label = previous_date.strftime("%d/%m/%Y")
        previous_key = (afm, previous_label)
        previous_rows = punches.get(previous_key, [])
        if not previous_rows:
            continue

        previous_starts = {
            value
            for row in previous_rows
            for value in [_minute_of_day(row.get("hour_from"))]
            if value is not None and _clock(row.get("hour_from"))
        }
        if len(previous_starts) != 1:
            continue
        assumed_start_abs = next(iter(previous_starts))

        target_previous_index = None
        latest_previous_end_abs = assumed_start_abs
        for index, item in enumerate(previous_rows):
            if _minute_of_day(item.get("hour_from")) != assumed_start_abs:
                continue
            end_abs = row_end_abs(previous_date, item)
            if end_abs is None:
                if target_previous_index is None:
                    target_previous_index = index
                continue
            if end_abs >= latest_previous_end_abs:
                latest_previous_end_abs = end_abs
                target_previous_index = index
        if target_previous_index is None:
            continue

        weekly_days = weekly_system_by_afm.get(afm, (None, ""))[0]
        daily_limit = 780 if weekly_days == 5 else 720 if weekly_days == 6 else None
        if daily_limit is None:
            continue
        _, _, outside_break = _break_context(
            contracts_by_afm.get(afm),
            schedules.get(previous_key, []),
            has_actual_work=True,
        )
        max_allowed_end_abs = assumed_start_abs + daily_limit + outside_break

        declared_starts = [
            _minutes_from_work_anchor(previous_date, current_date, item.get("hour_from"))
            for item in _working_slots(schedules.get(key, []))
            if _clock(item.get("hour_from"))
        ]
        new_shift_start_abs = min(
            (value for value in declared_starts if value is not None),
            default=None,
        )

        retained: list[dict[str, Any]] = []
        latest_carried_end_abs = latest_previous_end_abs
        for item in punches.get(key, []):
            start_abs = _minutes_from_work_anchor(previous_date, current_date, item.get("hour_from"))
            end_abs = (
                _minutes_from_work_anchor(
                    previous_date, current_date, item.get("hour_to"), after_abs=start_abs,
                )
                if start_abs is not None else None
            )
            covered = bool(
                start_abs is not None
                and end_abs is not None
                and not _is_explicit_next_day(item)
                and start_abs >= assumed_start_abs
                and end_abs <= max_allowed_end_abs
                and (new_shift_start_abs is None or start_abs < new_shift_start_abs)
            )
            if covered:
                excluded_from_current[key].append(item)
                attributed_to_previous[previous_key].append(item)
                if end_abs > latest_carried_end_abs:
                    latest_carried_end_abs = end_abs
                    next_day_end = latest_carried_end_abs >= 1440
                    previous_rows[target_previous_index] = {
                        **previous_rows[target_previous_index],
                        "hour_to": _hm(latest_carried_end_abs - 1440 if next_day_end else latest_carried_end_abs),
                        "is_end_date_different": 1 if next_day_end else 0,
                    }
            else:
                retained.append(item)
        if retained:
            punches[key] = retained
        else:
            punches.pop(key, None)
    return excluded_from_current, attributed_to_previous


def _possible_undeclared_split_parts(
    punches: list[dict[str, Any]],
    work_slots: list[dict[str, Any]],
    *,
    max_inferred_overnight_minutes: int | None,
) -> list[dict[str, Any]]:
    """Return two actual pairs that require review as a possible split shift."""
    if len(work_slots) != 1 or len(punches) != 2:
        return []
    intervals: list[tuple[int, int, dict[str, Any]]] = []
    for punch in punches:
        # A starred row plus a short next-calendar-day continuation has already
        # been assigned to one overnight work period; it is not a same-day split.
        if _is_explicit_next_day(punch):
            return []
        interval = _valid_punch_interval(
            punch,
            max_inferred_overnight_minutes=max_inferred_overnight_minutes,
        )
        if interval is None:
            return []
        intervals.append((interval[0], interval[1], punch))
    intervals.sort(key=lambda item: item[0])
    first, second = intervals
    if second[0] - first[1] < 180:
        return []
    return [
        {
            "from": _hm(start), "to": _hm(end),
            "inferred_from": False, "inferred_to": False, "punch": punch,
        }
        for start, end, punch in intervals
    ]


def _format_matched_label(matched: list[dict[str, Any]]) -> str:
    if not matched:
        return "—"
    return " · ".join(f"{m.get('from') or '—'}–{m.get('to') or '—'}" for m in matched)


def _build_status_explanation(
    *,
    status: str,
    reason: str,
    day_punches: list[dict[str, Any]],
    orphan_punches: list[dict[str, Any]],
    matched: list[dict[str, Any]],
    inferred: bool,
    fully_missing: bool,
    declared_label: str,
    actual_label: str,
    punch_recorded: str,
    proposed: str,
    proposal_basis: str,
    confidence: str,
    requires_confirmation: bool,
    contract_kind: str,
    break_minutes: int,
    break_in_work: int | None,
    classification_warning: str,
    flex: int,
    punch_count: int,
    matched_parts: int,
    single_schedule: bool,
    overtime_segments: list[dict[str, Any]],
    corrected_extra_punches: list[dict[str, Any]],
) -> list[str]:
    status_names = {"ok": "Σύμφωνο", "change": "Μεταβολή", "review": "Έλεγχος"}
    lines = [f"Αποτέλεσμα: {status_names.get(status, status)}", reason]

    if fully_missing:
        lines.append("Δεν υπάρχει καμία εγγραφή χτυπήματος στην κάρτα.")
    elif punch_recorded != "—":
        lines.append(f"Καταγεγραμμένα χτυπήματα ({punch_count}):")
        for item in day_punches:
            lines.append(f"  · {_format_recorded_punch(item)}")

    if punch_count > matched_parts and matched_parts and single_schedule:
        lines.append(
            f"Υπάρχουν {punch_count} εγγραφές σε μη σπαστό ωράριο· χρησιμοποιήθηκε το μεγαλύτερο έγκυρο πραγματικό διάστημα από έναρξη έως μεταγενέστερη λήξη ({actual_label}). Η ένδειξη * σημαίνει ρητά λήξη την επόμενη ημερολογιακή ημέρα."
        )
    elif punch_count > matched_parts and matched_parts:
        lines.append(
            f"Αντιστοιχίστηκαν {matched_parts} από {punch_count} εγγραφές με το δηλωμένο ωράριο ({declared_label})."
        )

    if orphan_punches:
        lines.append(f"Επιπλέον μη αντιστοιχισμένες εγγραφές ({len(orphan_punches)}):")
        for item in orphan_punches:
            lines.append(f"  · {_format_recorded_punch(item)}")

    for item in corrected_extra_punches:
        lines.append(
            f"Λανθασμένο πρόσθετο χτύπημα {_format_recorded_punch(item['recorded'])}: "
            f"η ελλιπής πλευρά κλείνει στην ίδια ώρα ({item['corrected']})."
        )

    if inferred and matched:
        for index, item in enumerate(matched, start=1):
            prefix = f"Τμήμα {index}: " if len(matched) > 1 else ""
            if item.get("inferred_from"):
                lines.append(f"{prefix}Λείπει είσοδος στην κάρτα — για υπολογισμό χρησιμοποιήθηκε δηλωμένη έναρξη ({item.get('from')}).")
            if item.get("inferred_to"):
                lines.append(f"{prefix}Λείπει έξοδος στην κάρτα — για υπολογισμό χρησιμοποιήθηκε δηλωμένη λήξη ({item.get('to')}).")

    if actual_label != punch_recorded and actual_label != "—" and inferred:
        lines.append(f"Για ώρες και διαφορές αξιολογήθηκε (τεκμαίρεται): {actual_label}")

    if proposed and proposed != declared_label:
        lines.append(f"Πρόταση απολογιστικού: {proposed} ({proposal_basis}).")
    elif status == "ok":
        lines.append(f"Πρόταση: διατήρηση δηλωμένου ωραρίου ({declared_label}).")

    if flex:
        lines.append(f"Ευέλικτη προσέλευση σύμβασης: {flex} λεπτά.")

    if contract_kind in ("Άγνωστη σύμβαση", "Μη προσδιορισμένη"):
        lines.append(f"Σύμβαση: {contract_kind} — απαιτείται χειροκίνητος έλεγχος.")

    if break_minutes and break_in_work is None:
        lines.append(
            f"Διάλειμμα {break_minutes} λεπτά χωρίς ρητή ένδειξη «εντός/εκτός» — δεν αφαιρέθηκε αυτόματα."
        )

    if classification_warning:
        lines.append(classification_warning)

    for segment in overtime_segments:
        lines.append(
            f"Υπερωρία προς υποβολή στις {segment['date']}: {segment['from']}–{segment['to']} ({segment['minutes']} λεπτά)."
        )

    lines.append(f"Βεβαιότητα: {confidence}.")
    if requires_confirmation:
        lines.append("Χρειάζεται επιβεβαίωση πριν από οποιαδήποτε δήλωση.")

    return lines


def _night_minutes(start: Any, end: Any) -> int:
    """Minutes overlapping 22:00–06:00, attributed to the start date."""
    a = _minute_of_day(start)
    b = _minute_of_day(end, after=a) if a is not None else None
    if a is None or b is None:
        return 0
    return sum(
        max(0, min(b, offset + 1800) - max(a, offset + 1320))
        for offset in (-1440, 0, 1440)
    )


def _schedule_text(slots: list[dict[str, Any]]) -> str:
    text = " ".join(str(s.get("shift_type") or "").upper() for s in slots)
    return "".join(
        char for char in unicodedata.normalize("NFD", text)
        if unicodedata.category(char) != "Mn"
    )


def _day_state(slots: list[dict[str, Any]]) -> str:
    # A report row with no schedule slots exists only because a punch was found.
    # For retrospective exchange purposes, treat that undeclared day as rest.
    if not slots:
        return "Ρεπό"
    text = _schedule_text(slots)
    if "ΤΗΛΕΡΓΑΣ" in text:
        return "Τηλεργασία"
    if "ΑΔΕΙΑ" in text:
        return "Άδεια"
    if any(marker in text for marker in REST_MARKERS):
        return "Ρεπό"
    if "ΜΗ ΕΡΓΑΣΙΑ" in text:
        return "Μη εργασία"
    if "ΑΡΓΙΑ" in text:
        return "Αργία"
    if _working_slots(slots) or "ΕΡΓΑΣΙΑ" in text:
        return "Εργασία"
    return "Χωρίς δηλωμένο ωράριο"


def _is_non_work(slots: list[dict[str, Any]]) -> bool:
    text = _schedule_text(slots)
    return any(marker in text for marker in NON_WORK_MARKERS)


def _working_slots(slots: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        [s for s in slots if _clock(s.get("hour_from")) and _clock(s.get("hour_to"))],
        key=lambda s: _minute_of_day(s.get("hour_from")) or 0,
    )


def _distance(punch: dict[str, Any], slot: dict[str, Any]) -> int:
    ds = _minute_of_day(slot.get("hour_from")) or 0
    de = _minute_of_day(slot.get("hour_to"), after=ds) or ds
    ps = _minute_of_day(punch.get("hour_from"))
    pe = _minute_of_day(punch.get("hour_to"), after=ps) if ps is not None else None
    return abs((ps if ps is not None else ds) - ds) + abs((pe if pe is not None else de) - de)


def _match_punches(
    punches: list[dict[str, Any]], slots: list[dict[str, Any]],
    *, max_inferred_overnight_minutes: int | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Match one card row per declared part; missing boundaries use declared ones."""
    declared = _working_slots(slots)
    if not declared:
        selected_span = _maximum_valid_punch_span(
            punches, max_inferred_overnight_minutes=max_inferred_overnight_minutes
        )
        if not selected_span:
            if len(punches) == 1:
                selected = punches[0]
                boundary = (
                    selected.get("hour_from") if _clock(selected.get("hour_from"))
                    else selected.get("hour_to") if _clock(selected.get("hour_to")) else None
                )
                if boundary:
                    return [{"from": boundary, "to": boundary,
                             "inferred_from": not bool(_clock(selected.get("hour_from"))),
                             "inferred_to": not bool(_clock(selected.get("hour_to"))),
                             "punch": selected}], []
            return [], []
        start, end, first_punch, last_punch = selected_span
        return [{"from": _hm(start), "to": _hm(end),
                 "inferred_from": False, "inferred_to": False,
                 "punch": first_punch, "last_punch": last_punch,
                 "extra_punches": [p for p in punches if p is not first_punch],
                 "envelope_from_multiple": len(punches) > 1}], []

    if len(declared) == 1 and punches:
        slot = declared[0]
        complete = [p for p in punches if _valid_punch_interval(
            p, max_inferred_overnight_minutes=max_inferred_overnight_minutes
        ) is not None]
        if complete and len(punches) > 1:
            selected_span = _maximum_valid_punch_span(
                punches, max_inferred_overnight_minutes=max_inferred_overnight_minutes
            )
            if not selected_span:
                return [], list(punches)
            actual_start, actual_end, first_punch, last_punch = selected_span
            return [{"from": _hm(actual_start), "to": _hm(actual_end),
                     "inferred_from": False, "inferred_to": False,
                     "punch": first_punch, "slot": slot,
                     "extra_punches": [p for p in punches if p is not first_punch],
                     "envelope_from_multiple": True, "last_punch": last_punch}], []
        pick = complete[0] if complete else min(punches, key=lambda p: _distance(p, slot))
        if (_clock(pick.get("hour_from")) and _clock(pick.get("hour_to"))
                and _valid_punch_interval(
                    pick, max_inferred_overnight_minutes=max_inferred_overnight_minutes
                ) is None):
            return [], list(punches)
        actual_from = pick.get("hour_from") if _clock(pick.get("hour_from")) else slot.get("hour_from")
        actual_to = pick.get("hour_to") if _clock(pick.get("hour_to")) else slot.get("hour_to")
        return [{"from": actual_from, "to": actual_to,
                 "inferred_from": not bool(_clock(pick.get("hour_from"))),
                 "inferred_to": not bool(_clock(pick.get("hour_to"))),
                 "punch": pick, "slot": slot,
                 "extra_punches": [p for p in punches if p is not pick]}], []

    available = list(punches)
    matched: list[dict[str, Any]] = []
    for slot in declared:
        pick = min(available, key=lambda p: _distance(p, slot)) if available else None
        if pick is not None:
            available.remove(pick)
        actual_from = pick.get("hour_from") if pick and _clock(pick.get("hour_from")) else slot.get("hour_from")
        actual_to = pick.get("hour_to") if pick and _clock(pick.get("hour_to")) else slot.get("hour_to")
        matched.append({
            "from": actual_from, "to": actual_to,
            "inferred_from": not bool(pick and _clock(pick.get("hour_from"))),
            "inferred_to": not bool(pick and _clock(pick.get("hour_to"))),
            "punch": pick, "slot": slot,
        })
    return matched, available


def _contract_kind(contract: dict[str, Any] | None) -> tuple[str, int | None]:
    if not contract:
        return "Άγνωστη σύμβαση", None
    text = " ".join(str(contract.get(k) or "").upper() for k in ("characterization", "regime", "employment_relation"))
    days_raw = str(contract.get("weekly_work_days") or "")
    days = next((n for n in (5, 6) if str(n) in days_raw), None)
    if "ΕΚ ΠΕΡΙΤΡΟΠ" in text:
        return "Εκ περιτροπής", days
    if "ΜΕΡΙΚ" in text:
        return "Μερική", days
    if "ΠΛΗΡ" in text:
        return "Πλήρης", days
    return "Μη προσδιορισμένη", days


def _contract_weekly_minutes(contract: dict[str, Any] | None) -> int | None:
    raw = (contract or {}).get("weekly_hours")
    if raw is None or str(raw).strip() == "":
        return None
    try:
        return max(0, int(round(float(str(raw).strip().replace(",", ".")) * 60)))
    except ValueError:
        return None


def _contract_date(value: object) -> date | None:
    text = str(value or "").strip()[:10]
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass
    return None


def _contract_for_day(candidates: list[dict[str, Any]], work_date: str) -> dict[str, Any] | None:
    """Choose the contract segment effective on this specific day."""
    target = datetime.strptime(work_date, "%d/%m/%Y").date()
    matching = []
    active_candidates = []
    for contract in candidates:
        hire = _contract_date(contract.get("hire_date"))
        departure = _contract_date(contract.get("departure_date"))
        if (hire is not None and target < hire) or (departure is not None and target > departure):
            continue
        start = _contract_date(contract.get("effective_from")) or hire
        end = _contract_date(contract.get("effective_to")) or departure
        rank = (start or date.min, int(contract.get("id") or 0), contract)
        active_candidates.append(rank)
        if (start is None or start <= target) and (end is None or target <= end):
            matching.append(rank)
    if matching:
        return max(matching, key=lambda item: item[:2])[2]
    # A first imported snapshot can post-date the requested period even though
    # the employment was already active. Use the earliest known snapshot.
    return min(active_candidates, key=lambda item: item[:2])[2] if active_candidates else None


def _is_catering_contract(contract: dict[str, Any] | None) -> bool:
    override = (contract or {}).get("catering_override")
    if override is not None:
        return override in (True, 1, "1", "true", "True")
    text = " ".join(str((contract or {}).get(key) or "") for key in (
        "specialty", "characterization", "employment_relation", "regime",
    )).upper()
    normalized = "".join(
        char for char in unicodedata.normalize("NFD", text)
        if unicodedata.category(char) != "Mn"
    )
    return "ΕΠΙΣΙΤ" in normalized


def _effective_weekly_days(
    schedule_rows: list[dict[str, Any]], contract_weekly_days: int | None,
) -> tuple[int | None, str]:
    """The employee's five/six-day system always comes from the contract."""
    del schedule_rows
    if contract_weekly_days in (5, 6):
        return contract_weekly_days, "Σύμβαση εργαζομένου"
    return None, "Μη προσδιορισμένο στη σύμβαση"


def _daily_overtime_basis(
    declared_minutes: int, contract_weekly_days: int | None,
) -> tuple[int | None, str]:
    """Resolve only the day's overtime bands; never the contractual weekly system."""
    if declared_minutes == 480:
        return 5, "Δηλωμένο ωράριο ημέρας ακριβώς 8:00"
    if declared_minutes == 400:
        return 6, "Δηλωμένο ωράριο ημέρας ακριβώς 6:40"
    if contract_weekly_days in (5, 6):
        return contract_weekly_days, "Σύμβαση εργαζομένου"
    return None, "Μη προσδιορισμένη ημερήσια βάση"


def _break_context(
    contract: dict[str, Any] | None,
    work_slots: list[dict[str, Any]],
    *,
    has_actual_work: bool = False,
) -> tuple[int, int | None, int]:
    raw = (contract or {}).get("break_minutes")
    if raw is None and work_slots:
        raw = work_slots[0].get("break_minutes")
    minutes = max(0, int(raw or 0))
    in_work = (contract or {}).get("break_in_work")
    if in_work is None and work_slots:
        in_work = work_slots[0].get("break_in_work")
    # Blank is not silently treated as outside: it needs confirmation.
    outside = minutes if (work_slots or has_actual_work) and in_work == 0 else 0
    return minutes, in_work, outside


def _contract_flags(contract: dict[str, Any] | None) -> dict[str, bool]:
    text = " ".join(str(value or "").upper() for value in (contract or {}).values())
    return {
        "work_arrangement": "ΔΙΕΥΘΕΤ" in text,
        "unpredictable_schedule": "ΜΗ ΠΡΟΒΛΕΨΙΜ" in text,
        "uneven_distribution": "ΑΝΙΣΟΜΕΡ" in text,
    }


def _classify_extra(contract_kind: str, weekly_days: int | None, worked: int, declared: int) -> dict[str, Any]:
    return classify_extra_minutes(contract_kind, weekly_days, worked, declared)


def _proposed_normal_slot(
    ds: int, de: int, ps: int, pe: int, declared_minutes: int,
    outside_break: int, flex: int, actual_minutes: int,
) -> tuple[int, int, str]:
    if actual_minutes <= declared_minutes and pe > de + flex:
        # Suspected late/missed entry: anchor backwards from the real exit.
        # Outside break extends physical presence but not the declared schedule slot.
        work_end = pe - outside_break
        return work_end - declared_minutes, work_end, "Ανάστροφα από την πραγματική λήξη"
    return ps, ps + declared_minutes, "Από την πραγματική έναρξη"


def _overtime_segments(work_date: str, start: int | None, end: int | None) -> list[dict[str, Any]]:
    """Assign the whole overtime interval to the date on which overtime starts.

    The interval may itself cross midnight (for example 23:00–01:00).  It is
    not split, because the submission date is determined by its starting
    instant rather than by every calendar day touched by the interval.
    """
    if start is None or end is None or end <= start:
        return []
    base = datetime.strptime(work_date, "%d/%m/%Y").date()
    segment_date = base + timedelta(days=start // 1440)
    return [{
        "date": segment_date.strftime("%d/%m/%Y"),
        "from": _hm(start),
        "to": _hm(end),
        "minutes": end - start,
    }]


def build_weekly_report(
    schedule_rows: list[dict[str, Any]], work_rows: list[dict[str, Any]], contracts: list[dict[str, Any]],
    *,
    sunday_rest_transfer_enabled: bool = False,
    uneven_distribution_enabled: bool = False,
    holiday_dates: set | None = None,
) -> dict[str, Any]:
    schedules: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    punches: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    contract_segments_by_afm: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for contract_row in contracts:
        contract_segments_by_afm[str(contract_row.get("employee_afm") or "").zfill(9)].append(contract_row)
    contracts_by_afm = {
        afm: next((row for row in segments if row.get("is_current") in (True, 1, "1")), segments[-1])
        for afm, segments in contract_segments_by_afm.items()
    }
    names: dict[str, tuple[str, str]] = {}
    for source, target in ((schedule_rows, schedules), (work_rows, punches)):
        for row in source:
            afm = str(row.get("employee_afm") or "").zfill(9)
            target[(afm, str(row.get("work_date") or ""))].append(row)
            names[afm] = (str(row.get("eponymo") or ""), str(row.get("onoma") or ""))

    schedules_by_afm: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in schedule_rows:
        schedules_by_afm[str(row.get("employee_afm") or "").zfill(9)].append(row)

    weekly_system_by_afm: dict[str, tuple[int | None, str]] = {}
    for afm in set(schedules_by_afm) | set(contracts_by_afm):
        _, contract_weekly_days = _contract_kind(contracts_by_afm.get(afm))
        weekly_system_by_afm[afm] = _effective_weekly_days(
            schedules_by_afm.get(afm, []), contract_weekly_days
        )

    excluded_by_previous_overnight, carried_into_previous = (
        _partition_punches_covered_by_previous_overnight(
            punches, schedules, contracts_by_afm, weekly_system_by_afm
        )
    )

    punch_dates_by_afm: dict[str, set[str]] = defaultdict(set)
    for afm, work_date in punches:
        if punches[(afm, work_date)]:
            punch_dates_by_afm[afm].add(work_date)
    weekly_punch_details_by_afm: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for (afm, work_date), day_rows in punches.items():
        if day_rows:
            weekly_punch_details_by_afm[afm].append({
                "work_date": work_date,
                "punches": [_format_recorded_punch(item) for item in day_rows],
            })
    for rows in weekly_punch_details_by_afm.values():
        rows.sort(key=lambda item: datetime.strptime(item["work_date"], "%d/%m/%Y"))
    missing_declared_by_afm: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for (afm, work_date), slots in schedules.items():
        working = _working_slots(slots)
        if working and not punches.get((afm, work_date)):
            missing_declared_by_afm[afm].append({
                "work_date": work_date,
                "declared": " · ".join(f"{slot.get('hour_from')}–{slot.get('hour_to')}" for slot in working),
                "declared_minutes": sum(
                    _minutes(slot.get("hour_from"), slot.get("hour_to")) or 0
                    for slot in working
                ),
            })
    for rows in missing_declared_by_afm.values():
        rows.sort(key=lambda item: datetime.strptime(item["work_date"], "%d/%m/%Y"))

    daily: list[dict[str, Any]] = []
    for afm, work_date in sorted(set(schedules) | set(punches), key=lambda k: (datetime.strptime(k[1], "%d/%m/%Y"), names.get(k[0], ("", "")), k[0])):
        slots, day_punches = schedules.get((afm, work_date), []), punches.get((afm, work_date), [])
        # A declared leave day without card activity is already self-explanatory:
        # it requires neither retrospective action nor an informational row.
        if slots and not day_punches and _day_state(slots) == "Άδεια":
            continue
        excluded_overnight_punches = excluded_by_previous_overnight.get((afm, work_date), [])
        carried_overnight_punches = carried_into_previous.get((afm, work_date), [])
        work_slots = _working_slots(slots)
        contract = _contract_for_day(contract_segments_by_afm.get(afm, []), work_date)
        contract_kind, _contract_weekly_days = _contract_kind(contract)
        max_inferred_overnight_minutes = (
            780 if _contract_weekly_days == 5 else 720 if _contract_weekly_days == 6 else None
        )
        matched, orphan_punches = _match_punches(
            day_punches, slots,
            max_inferred_overnight_minutes=max_inferred_overnight_minutes,
        )
        possible_split_parts = _possible_undeclared_split_parts(
            day_punches,
            work_slots,
            max_inferred_overnight_minutes=max_inferred_overnight_minutes,
        )
        if possible_split_parts:
            matched, orphan_punches = possible_split_parts, []
        fully_missing = bool(work_slots and not day_punches)
        if fully_missing:
            # A declaration without any card record is not evidence of actual work.
            matched = []
        extra_punches = matched[0].get("extra_punches", []) if len(_working_slots(slots)) == 1 and matched else []
        corrected_extra_punches = []
        for extra in extra_punches:
            extra_from = _format_recorded_boundary(extra.get("hour_from"))
            extra_to = _format_recorded_boundary(extra.get("hour_to"))
            if bool(extra_from) != bool(extra_to):
                boundary = extra_from or extra_to
                corrected_extra_punches.append({"recorded": extra, "from": boundary, "to": boundary,
                                                "corrected": f"{boundary}–{boundary}"})
        if _contract_weekly_days in (5, 6):
            weekly_days, weekly_days_source = (
                _contract_weekly_days, "Σύμβαση εργαζομένου"
            )
        else:
            weekly_days, weekly_days_source = weekly_system_by_afm.get(
                afm, (None, "Μη προσδιορισμένο στη σύμβαση")
            )
        contract_flags = _contract_flags(contract)
        declared_minutes = sum(_minutes(s.get("hour_from"), s.get("hour_to")) or 0 for s in work_slots)
        daily_overtime_days, daily_overtime_basis_source = _daily_overtime_basis(
            declared_minutes, _contract_weekly_days
        )
        if contract_kind == "Μερική":
            daily_overtime_days = None
            daily_overtime_basis_source = "Δεν εφαρμόζεται στη μερική απασχόληση"
        classification_days = (
            daily_overtime_days
            if contract_kind in ("Πλήρης", "Εκ περιτροπής")
            else weekly_days
        )
        actual_minutes = sum(_minutes(m.get("from"), m.get("to")) or 0 for m in matched) if matched else None
        inferred = any(m.get("inferred_from") or m.get("inferred_to") for m in matched)
        declared_label = " · ".join(f"{s.get('hour_from')}–{s.get('hour_to')}" for s in work_slots) or (str(slots[0].get("shift_type") or "") if slots else "ΑΝΑΠΑΥΣΗ/ΡΕΠΟ")
        punch_recorded = _format_recorded_punches(day_punches)
        actual_label = _format_matched_label(matched)
        flex = int((contract or {}).get("flex_arrival_minutes") or (work_slots[0].get("flex_arrival_minutes") if work_slots else 0) or 0)
        break_minutes, break_in_work, outside_break = _break_context(
            contract, work_slots, has_actual_work=bool(actual_minutes and actual_minutes > 0)
        )
        effective_actual = max(0, (actual_minutes or 0) - outside_break) if actual_minutes is not None else None
        gross_difference = actual_minutes - declared_minutes if actual_minutes is not None else None
        net_difference = effective_actual - declared_minutes if effective_actual is not None else None
        first = matched[0] if matched else None
        last = matched[-1] if matched else None
        ds = _minute_of_day(work_slots[0].get("hour_from")) if work_slots else None
        de = _minute_of_day(work_slots[-1].get("hour_to"), after=ds) if work_slots and ds is not None else None
        ps = _minute_of_day(first.get("from")) if first else None
        pe = _minute_of_day(last.get("to"), after=ps) if last and ps is not None else None
        overtime_ps, overtime_pe = _overtime_interval_before_general_validation(
            day_punches, slots, matched
        )
        overtime_actual_minutes = (
            overtime_pe - overtime_ps
            if overtime_ps is not None and overtime_pe is not None and overtime_pe > overtime_ps
            else 0
        )
        overtime_effective_actual = max(0, overtime_actual_minutes - outside_break)
        start_difference = ps - ds if ps is not None and ds is not None else None
        end_difference = pe - de if pe is not None and de is not None else None
        bands = _classify_extra(
            contract_kind, classification_days, overtime_effective_actual, declared_minutes
        )
        if contract_flags["work_arrangement"]:
            bands["classification_warning"] = "Διευθέτηση χρόνου εργασίας: απαιτείται έλεγχος περιόδου αναφοράς και ορίου 10 ωρών"
        elif contract_flags["uneven_distribution"]:
            bands["classification_warning"] = "Ανισομερής κατανομή: απαιτείται επιβεβαίωση της νόμιμης βάσης και του εβδομαδιαίου συνόλου"

        decision = RuleDecision("review", "Η περίπτωση δεν καλύπτεται από γνωστό κανόνα", actual_label, "Χειροκίνητος έλεγχος", "UNKNOWN_CASE_REVIEW")
        status, reason, proposed, proposal_basis, rule_id = (
            decision.status, decision.reason, decision.proposed, decision.proposal_basis, decision.rule_id
        )
        state = _day_state(slots)
        replacement_candidates: list[dict[str, Any]] = []
        exchange_options: list[dict[str, Any]] = []
        non_work_to_work_duration_rule: str | None = None
        weekly_punch_details: list[dict[str, Any]] = []
        weekly_punch_days: int | None = None
        contract_required_days: int | None = _contract_weekly_days
        special_non_work_punch = bool(
            matched and state in ("Μη εργασία", "Ρεπό") and day_punches
            and (bool(slots) or not inferred)
        )
        parsed_work_date = datetime.strptime(work_date, "%d/%m/%Y").date()
        _is_rest_day = parsed_work_date.weekday() == 6 or (holiday_dates and parsed_work_date in holiday_dates)
        compensatory_rest_due = bool(
            sunday_rest_transfer_enabled
            and _is_rest_day
            and contract_required_days == 5
            and len(punch_dates_by_afm.get(afm, set())) >= 6
            and (effective_actual or 0) > 300
            and day_punches
        )
        missing_start = bool(len(day_punches) == 1 and not _clock(day_punches[0].get("hour_from")) and _clock(day_punches[0].get("hour_to")))
        missing_end = bool(len(day_punches) == 1 and _clock(day_punches[0].get("hour_from")) and not _clock(day_punches[0].get("hour_to")))
        # A clock wrap is accepted when explicitly marked (*) or when it forms
        # a positive overnight interval within the contractual daily limit.
        raw_overnight = False
        declared_overnight = bool(
            work_slots and _minute_of_day(work_slots[-1].get("hour_to")) is not None
            and _minute_of_day(work_slots[0].get("hour_from")) is not None
            and (_minute_of_day(work_slots[-1].get("hour_to")) or 0) < (_minute_of_day(work_slots[0].get("hour_from")) or 0)
        )
        if possible_split_parts:
            first_start = _minute_of_day(possible_split_parts[0].get("from"))
            first_end = _minute_of_day(possible_split_parts[0].get("to"), after=first_start)
            second_start = _minute_of_day(possible_split_parts[1].get("from"), after=first_end)
            split_decision = (
                split_schedule_decision(
                    contract_kind=contract_kind,
                    daily_base=contract_daily_base_minutes(contract_kind, classification_days),
                    first_start=first_start,
                    first_end=first_end,
                    second_start=second_start,
                    outside_break=outside_break,
                    hm=_hm,
                )
                if first_start is not None and first_end is not None and second_start is not None
                else RuleDecision("review", "Μη έγκυρα όρια πιθανού σπαστού", "", "Χειροκίνητος έλεγχος", "POSSIBLE_SPLIT_INVALID_BOUNDARIES")
            )
            decision = RuleDecision(
                "review",
                "ΠΙΘΑΝΟ ΣΠΑΣΤΟ ΩΡΑΡΙΟ",
                split_decision.proposed,
                (
                    f"{split_decision.proposal_basis} · απαιτείται επιβεβαίωση"
                    if split_decision.proposal_basis else "Εφαρμογή κανόνων σπαστού μετά από επιβεβαίωση"
                ),
                "POSSIBLE_SPLIT_REVIEW",
            )
        elif len(work_slots) > 1:
            if len(matched) >= 2 and not inferred and not orphan_punches:
                first_start = _minute_of_day(matched[0].get("from"))
                first_end = _minute_of_day(matched[0].get("to"), after=first_start)
                second_start = _minute_of_day(matched[1].get("from"), after=first_end)
                if first_start is not None and first_end is not None and second_start is not None:
                    decision = split_schedule_decision(
                        contract_kind=contract_kind,
                        daily_base=contract_daily_base_minutes(contract_kind, classification_days),
                        first_start=first_start,
                        first_end=first_end,
                        second_start=second_start,
                        outside_break=outside_break,
                        hm=_hm,
                    )
                else:
                    decision = RuleDecision("review", "Μη έγκυρα όρια σπαστού", actual_label, "Χειροκίνητος έλεγχος", "SPLIT_INVALID_BOUNDARIES")
            else:
                decision = RuleDecision("review", "Σπαστό με ελλιπές ή ορφανό χτύπημα", actual_label, "Χειροκίνητος έλεγχος", "SPLIT_INCOMPLETE_REVIEW")
        else:
            decision = normal_schedule_decision(
                contract_kind=contract_kind,
                weekly_days=(classification_days if contract_kind in ("Πλήρης", "Εκ περιτροπής") else weekly_days),
                day_state=state,
                declared_label=declared_label,
                declared_minutes=declared_minutes,
                actual_label=actual_label,
                actual_minutes=actual_minutes,
                effective_actual=effective_actual,
                declared_start=ds,
                declared_end=de,
                actual_start=ps,
                actual_end=pe,
                flex=flex,
                outside_break=outside_break,
                has_punch=bool(day_punches),
                missing_start=missing_start,
                missing_end=missing_end,
                unpredictable=contract_flags["unpredictable_schedule"],
                raw_overnight=raw_overnight,
                declared_overnight=declared_overnight,
                hm=_hm,
            )
        if (
            excluded_overnight_punches
            and len(work_slots) == 1
            and ps is not None
            and declared_minutes > 0
            and not possible_split_parts
        ):
            post_carry_proposed = f"{_hm(ps)}–{_hm(ps + declared_minutes)}"
            if post_carry_proposed == declared_label:
                decision = RuleDecision(
                    "ok",
                    "Η πραγματική βάρδια συμφωνεί με το δηλωμένο (μετά τη μεταφορά νυχτερινής συνέχειας)",
                    declared_label,
                    "Πραγματική έναρξη = δηλωμένη",
                    "POST_CARRY_COMPLIANT",
                )
            else:
                decision = RuleDecision(
                    "change",
                    "Μετά τη μεταφορά της συνέχειας στην προηγούμενη ημέρα, η νέα βάρδια υπολογίστηκε από την πραγματική έναρξη",
                    post_carry_proposed,
                    "Πραγματική έναρξη κύριας βάρδιας και δηλωμένη διάρκεια",
                    "POST_CARRY_MAIN_SHIFT",
                )
        status, reason, proposed, proposal_basis, rule_id = (
            decision.status, decision.reason, decision.proposed, decision.proposal_basis, decision.rule_id
        )
        if len(work_slots) > 1 and status == "change" and proposed == declared_label and bands["overtime_minutes"] == 0:
            status, reason, rule_id = "ok", "Το πραγματικό σπαστό συμφωνεί με το δηλωμένο", "SPLIT_COMPLIANT"
        if status == "ok" and bands["overtime_minutes"] > 0:
            status, reason, rule_id = "change", "Το ωράριο είναι αποδεκτό αλλά απαιτείται απολογιστική υπερωρία", "OVERTIME_ONLY"
        if orphan_punches and len(work_slots) == 1:
            status, reason, rule_id = "review", "Υπάρχουν επιπλέον ορφανές εγγραφές χτυπημάτων", "ORPHAN_PUNCH_REVIEW"

        if special_non_work_punch:
            weekly_punch_days = len(punch_dates_by_afm.get(afm, set()))
            weekly_punch_details = list(weekly_punch_details_by_afm.get(afm, []))
            replacement_candidates = list(missing_declared_by_afm.get(afm, []))
            if ps is not None:
                exchange_options = [{
                    "rest_work_date": work_date,
                    "rest_punch": actual_label,
                    "replacement_work_date": item["work_date"],
                    "replacement_declared": item["declared"],
                    "replacement_proposed": (
                        "ΜΗ ΕΡΓΑΣΙΑ" if state == "Μη εργασία" else "ΑΝΑΠΑΥΣΗ/ΡΕΠΟ"
                    ),
                    "contract_duration_minutes": item["declared_minutes"],
                    "proposed": f"{_hm(ps)}–{_hm(ps + item['declared_minutes'])}",
                } for item in replacement_candidates if item.get("declared_minutes")]
            if exchange_options:
                status, rule_id = "review", "REST_WORK_EXCHANGE_REVIEW"
                proposed = exchange_options[0]["proposed"]
                proposal_basis = "Ανταλλαγή με δηλωμένη εργάσιμη ημέρα χωρίς χτύπημα"
                reason = f"Χτύπημα σε {state} και δηλωμένη εργάσιμη ημέρα χωρίς χτύπημα· απαιτείται επιλογή ανταλλαγής"
            else:
                status, rule_id = "change", "NON_WORK_DAY_BECOMES_WORK"
                reason = f"Χτύπημα σε {state} χωρίς διαθέσιμη ημέρα ανταλλαγής"
                full_day_cap = contract_daily_base_minutes(
                    contract_kind, _contract_weekly_days
                )
                if contract_kind == "Μερική":
                    non_work_to_work_duration_rule = (
                        "PARTIAL_PUNCH_DURATION_CAPPED_AT_FULL_DAY"
                    )
                elif contract_kind in ("Πλήρης", "Εκ περιτροπής"):
                    non_work_to_work_duration_rule = (
                        "PUNCH_DURATION_BELOW_CONTRACT_BASE"
                        if full_day_cap is not None
                        and (effective_actual or 0) < full_day_cap
                        else "CONTRACT_BASE_WITH_EXTRA_CLASSIFICATION"
                    )

        max_span = 780 if _contract_weekly_days == 5 else 720 if _contract_weekly_days == 6 else None
        exceeds_daily_span = bool(
            max_span is not None and actual_minutes is not None and actual_minutes > max_span
        )
        if exceeds_daily_span:
            status = "review"
            rule_id = "MAX_DAILY_SPAN_REVIEW"
            reason = (
                f"Το διάστημα χτυπήματος υπερβαίνει το όριο {max_span // 60} ωρών· "
                "η πρόταση υπολογίστηκε με τους κανονικούς κανόνες και απαιτεί έλεγχο"
            )

        overtime_from = overtime_to = None
        if bands["overtime_minutes"] and overtime_ps is not None and overtime_pe is not None:
            contract_base = contract_daily_base_minutes(contract_kind, classification_days)
            if (len(work_slots) > 1 or possible_split_parts) and " · " in proposed:
                last_part = proposed.split(" · ")[-1]
                proposed_second_start, proposed_second_end = last_part.split("–", 1)
                second_anchor = _minute_of_day(proposed_second_start, after=overtime_ps)
                proposed_end = _minute_of_day(proposed_second_end, after=second_anchor)
                overwork_window = 60 if contract_kind == "Πλήρης" and classification_days == 5 else 80 if contract_kind == "Πλήρης" and classification_days == 6 else 0
                overtime_from = (proposed_end + overwork_window) if proposed_end is not None else None
            else:
                threshold = 540 if contract_kind == "Πλήρης" and classification_days == 5 else 480 if contract_kind == "Πλήρης" and classification_days == 6 else (contract_base or declared_minutes)
                overtime_from = overtime_ps + outside_break + threshold
            if overtime_from is not None:
                overtime_to = min(overtime_pe, overtime_from + bands["overtime_minutes"])
        overtime_segments = _overtime_segments(work_date, overtime_from, overtime_to)
        requires_confirmation = (status != "ok" or contract_kind in ("Άγνωστη σύμβαση", "Μη προσδιορισμένη")
                                 or break_in_work is None and break_minutes > 0
                                 or contract_flags["work_arrangement"] or contract_flags["uneven_distribution"])
        confidence = "Χαμηλή" if requires_confirmation else ("Μέση" if len(day_punches) > len(work_slots) else "Υψηλή")
        orphan_details = [
            {"from": _format_recorded_boundary(p.get("hour_from")) or None,
             "to": _format_recorded_boundary(p.get("hour_to")) or None,
             "label": _format_recorded_punch(p)}
            for p in orphan_punches
        ]
        status_explanation = _build_status_explanation(
            status=status, reason=reason, day_punches=day_punches, orphan_punches=orphan_punches,
            matched=matched, inferred=inferred, fully_missing=fully_missing,
            declared_label=declared_label, actual_label=actual_label, punch_recorded=punch_recorded,
            proposed=proposed, proposal_basis=proposal_basis, confidence=confidence,
            requires_confirmation=requires_confirmation, contract_kind=contract_kind,
            break_minutes=break_minutes, break_in_work=break_in_work,
            classification_warning=bands.get("classification_warning") or "",
            flex=flex, punch_count=len(day_punches), matched_parts=len(matched),
            single_schedule=len(work_slots) == 1 and not possible_split_parts,
            overtime_segments=overtime_segments,
            corrected_extra_punches=corrected_extra_punches,
        )
        if excluded_overnight_punches:
            previous_date = (
                datetime.strptime(work_date, "%d/%m/%Y").date() - timedelta(days=1)
            ).strftime("%d/%m/%Y")
            status_explanation.append(
                f"Δεν συμμετείχαν στο κύριο χτύπημα της ημέρας {len(excluded_overnight_punches)} "
                f"εγγραφές πριν από τη λήξη της διανυκτερεύουσας βάρδιας της {previous_date}: "
                + " · ".join(_format_recorded_punch(item) for item in excluded_overnight_punches)
            )
        if carried_overnight_punches:
            status_explanation.append(
                "Πρόσθετα χτυπήματα της επόμενης ημερολογιακής ημέρας που αποδόθηκαν "
                "στην παρούσα διανυκτερεύουσα βάρδια: "
                + " · ".join(_format_recorded_punch(item) for item in carried_overnight_punches)
            )
        if contract_kind != "Μερική":
            basis_label = (
                _hm(contract_daily_base_minutes(contract_kind, daily_overtime_days))
                if daily_overtime_days in (5, 6)
                else "μη προσδιορισμένη"
            )
            status_explanation.append(
                f"Ημερήσια βάση υπερωρίας: {basis_label} ({daily_overtime_basis_source})."
            )
        if special_non_work_punch:
            status_explanation.extend([
                f"Εβδομαδιαίος έλεγχος: μετρήθηκαν {weekly_punch_days} διαφορετικές ημέρες με χτύπημα κάρτας.",
                f"Η τρέχουσα σύμβαση προβλέπει {contract_required_days if contract_required_days else 'άγνωστο αριθμό'} ημέρες απασχόλησης.",
                "Αναλυτικές ημέρες και χτυπήματα κάρτας της εβδομάδας:",
            ])
            status_explanation.extend(
                f"  · {item['work_date']}: {' · '.join(item['punches'])}"
                for item in weekly_punch_details
            )
            if replacement_candidates:
                status_explanation.append("Δηλωμένες ημέρες εργασίας χωρίς χτύπημα που μπορούν να εξεταστούν για αντικατάσταση:")
                status_explanation.extend(
                    f"  · {item['replacement_work_date']}: {item['replacement_declared']} "
                    f"({_hm(item['contract_duration_minutes'])} διάρκεια) ↔ {work_date}: "
                    f"πρόταση {item['proposed']}"
                    for item in exchange_options
                )
            else:
                status_explanation.append("Δεν βρέθηκε δηλωμένη εργάσιμη ημέρα χωρίς χτύπημα· προτείνεται μεταβολή της συγκεκριμένης ημέρας σε εργασία.")
        daily.append({
            "employee_afm": afm, "eponymo": names.get(afm, ("", ""))[0], "onoma": names.get(afm, ("", ""))[1],
            "work_date": work_date, "contract_kind": contract_kind, "weekly_days": weekly_days,
            "contract_weekly_minutes": _contract_weekly_minutes(contract),
            "contract_specialty": contract.get("specialty") if contract else None,
            "catering_override": contract.get("catering_override") if contract else None,
            "is_catering": _is_catering_contract(contract),
            "employment_start_date": contract.get("hire_date") if contract else None,
            "employment_end_date": contract.get("departure_date") if contract else None,
            "contract_effective_from": contract.get("effective_from") if contract else None,
            "contract_effective_to": contract.get("effective_to") if contract else None,
            "weekly_days_source": weekly_days_source,
            "actual_start_minutes": ps,
            "declared_start_minutes": ds,
            "daily_overtime_basis_days": daily_overtime_days,
            "daily_overtime_basis_minutes": contract_daily_base_minutes(contract_kind, daily_overtime_days),
            "daily_overtime_basis_source": daily_overtime_basis_source,
            **contract_flags,
            "declared": declared_label, "punch_recorded": punch_recorded,
            "actual": actual_label, "proposed": proposed,
            "proposed_schedule_type": "ΤΗΛ" if state == "Τηλεργασία" else None,
            "proposal_basis": proposal_basis, "rule_id": rule_id, "status": status, "reason": reason,
            "status_explanation": status_explanation, "orphan_punches": orphan_details,
            "excluded_by_previous_overnight": [
                {"from": _format_recorded_boundary(item.get("hour_from")) or None,
                 "to": _format_recorded_boundary(item.get("hour_to")) or None,
                 "label": _format_recorded_punch(item)}
                for item in excluded_overnight_punches
            ],
            "carried_overnight_punches": [
                {"from": _format_recorded_boundary(item.get("hour_from")) or None,
                 "to": _format_recorded_boundary(item.get("hour_to")) or None,
                 "label": _format_recorded_punch(item)}
                for item in carried_overnight_punches
            ],
            "corrected_extra_punches": [{k: v for k, v in item.items() if k != "recorded"}
                                         for item in corrected_extra_punches],
            "declared_minutes": declared_minutes, "actual_minutes": actual_minutes,
            "overtime_worked_minutes": overtime_actual_minutes,
            "effective_actual_minutes": effective_actual, "extra_minutes": max(0, net_difference or 0),
            "punch_count": len(day_punches), "matched_parts": len(matched), "orphan_punch_count": len(orphan_punches),
            "day_state": state, "punch_completeness": "Τεκμαρτό" if inferred else ("Πλήρες" if matched else "Χωρίς χτύπημα"),
            "data_source": "Πραγματική + δηλωμένα όρια" if inferred else ("Πραγματική απασχόληση" if matched else "Μόνο δηλωμένο ωράριο"),
            "flex_minutes": flex, "start_difference_minutes": start_difference, "end_difference_minutes": end_difference,
            "gross_difference_minutes": gross_difference, "break_minutes": break_minutes,
            "break_in_work": break_in_work, "outside_break_minutes": outside_break,
            "net_difference_minutes": net_difference,
            "night_minutes": sum(_night_minutes(m.get("from"), m.get("to")) for m in matched),
            **bands, "overtime_candidate_minutes": bands["overtime_minutes"],
            "overtime_from": _hm(overtime_from) if overtime_from is not None else None,
            "overtime_to": _hm(overtime_to) if overtime_to is not None else None,
            "overtime_segments": overtime_segments,
            "overnight": bool(first and _minutes(first.get("from"), first.get("to")) is not None and (_minute_of_day(first.get("to")) or 0) < (_minute_of_day(first.get("from")) or 0)),
            "requires_confirmation": requires_confirmation, "confidence": confidence,
            "sixth_day_candidate": False, "suggested_rest": False,
            "weekly_punch_days": weekly_punch_days,
            "contract_required_days": contract_required_days,
            "replacement_candidates": replacement_candidates,
            "exchange_options": exchange_options,
            "non_work_to_work_duration_rule": non_work_to_work_duration_rule,
            "weekly_punch_details": weekly_punch_details,
            "compensatory_rest_due": compensatory_rest_due,
            "compensatory_rest_target_week": (
                (parsed_work_date + timedelta(days=1)).isoformat()
                if compensatory_rest_due else None
            ),
        })

    # Propose exactly the contractual surplus of declared workdays as rest, never auto-apply.
    by_employee: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in daily:
        by_employee[row["employee_afm"]].append(row)
    for afm, rows in by_employee.items():
        declared_workdays = [r for r in rows if r["declared_minutes"] > 0]
        _, contract_days = _contract_kind(contracts_by_afm.get(afm))
        surplus = max(0, len(declared_workdays) - int(contract_days or len(declared_workdays)))
        missing = [r for r in declared_workdays if r["punch_count"] == 0]
        for row in missing[:surplus]:
            rest_reason = (
                f"{len(declared_workdays)} δηλωμένες εργάσιμες έναντι {contract_days} ημερών σύμβασης: "
                "πρόταση ρεπό με έγκριση"
            )
            row.update(status="review", reason=rest_reason, rule_id="SURPLUS_DECLARED_DAY_REST",
                       proposed="ΑΝΑΠΑΥΣΗ/ΡΕΠΟ", suggested_rest=True,
                       requires_confirmation=True, confidence="Χαμηλή",
                       status_explanation=["Αποτέλεσμα: Έλεγχος", rest_reason,
                                           "Δεν υπάρχει καμία εγγραφή χτυπήματος στην κάρτα.",
                                           "Πρόταση: ΑΝΑΠΑΥΣΗ/ΡΕΠΟ (μόνο με έγκριση).",
                                           "Βεβαιότητα: Χαμηλή.", "Χρειάζεται επιβεβαίωση πριν από οποιαδήποτε δήλωση."])

        # If non-work punches outnumber missing declared workdays, only the
        # earliest rows up to the available replacements remain exchange reviews.
        exchange_rows = sorted(
            [r for r in rows if r.get("exchange_options")],
            key=lambda r: datetime.strptime(r["work_date"], "%d/%m/%Y"),
        )
        available_replacements = len({
            option["replacement_work_date"]
            for row in exchange_rows for option in row.get("exchange_options") or []
        })
        for row in exchange_rows[available_replacements:]:
            row.update(status="change", rule_id="NON_WORK_DAY_BECOMES_WORK",
                       reason="Χτύπημα σε ημέρα μη εργασίας χωρίς διαθέσιμη επιπλέον ανταλλαγή",
                       exchange_options=[], replacement_candidates=[])

        if uneven_distribution_enabled:
            contract_kind, distribution_days = _contract_kind(contracts_by_afm.get(afm))
            plans = (allocate_uneven_distribution(
                employee_afm=afm, rows=rows, weekly_days=distribution_days,
            ) if contract_kind == "Πλήρης" else [])
            for plan in plans:
                members = []
                for member in rows:
                    member_date = str(member.get("work_date") or "")
                    if member_date not in plan["member_deltas"]:
                        continue
                    delta = int(plan["member_deltas"][member_date])
                    before = int(member.get("declared_minutes") or 0)
                    after = before + delta
                    start = member.get("actual_start_minutes") if delta > 0 else member.get("declared_start_minutes")
                    if start is None:
                        members = []
                        break
                    members.append({
                        "work_date": member_date,
                        "declared": member.get("declared"),
                        "proposed": f"{_hm(int(start))}–{_hm(int(start) + after)}",
                        "before_minutes": before,
                        "after_minutes": after,
                        "delta_minutes": delta,
                        "role": "target" if delta > 0 else "donor",
                    })
                if len(members) != len(plan["member_deltas"]):
                    continue
                by_date = {item["work_date"]: item for item in members}
                for member in rows:
                    detail = by_date.get(str(member.get("work_date") or ""))
                    if not detail:
                        continue
                    member.update(
                        status="review",
                        rule_id=("UNEVEN_DISTRIBUTION_TARGET_REVIEW" if detail["delta_minutes"] > 0
                                 else "UNEVEN_DISTRIBUTION_DONOR_REVIEW"),
                        reason="Πρόταση ισοσκελισμένης ανισομερούς κατανομής εβδομάδας",
                        proposed=detail["proposed"],
                        proposal_basis="Πραγματική έναρξη και εβδομαδιαία εξισορρόπηση 40:00",
                        requires_confirmation=True,
                        confidence="Μέση",
                        uneven_distribution_group={**plan, "role": detail["role"],
                                                   "delta_minutes": detail["delta_minutes"],
                                                   "members": members},
                        status_explanation=[
                            "Αποτέλεσμα: Έλεγχος",
                            "Πρόταση ανισομερούς κατανομής με ακριβές εβδομαδιαίο ισοζύγιο.",
                            f"Δηλωμένο εβδομαδιαίο σύνολο πριν: {_hm(plan['weekly_before_minutes'])}.",
                            f"Δηλωμένο εβδομαδιαίο σύνολο μετά: {_hm(plan['weekly_after_minutes'])}.",
                            f"Μεταβολή ημέρας: {detail['delta_minutes']:+d} λεπτά.",
                            "Η ομάδα πρέπει να εγκριθεί ολόκληρη πριν από οποιαδήποτε δήλωση.",
                        ],
                    )

    summaries = []
    for afm, rows in by_employee.items():
        overwork = sum(r["overwork_minutes"] for r in rows)
        overtime = sum(r["overtime_minutes"] for r in rows)
        contract_kind, contract_weekly_days = _contract_kind(contracts_by_afm.get(afm))
        weekly_days, weekly_days_source = weekly_system_by_afm.get(
            afm, (contract_weekly_days, "Τρέχουσα σύμβαση")
        )
        weekly_warning = ""
        cap = 300 if weekly_days == 5 else 480 if weekly_days == 6 else None
        if cap is not None and overwork > cap:
            weekly_warning = "Υπέρβαση εβδομαδιαίου ορίου υπερεργασίας"
        elif overwork and sum(r["effective_actual_minutes"] or 0 for r in rows) <= 2400:
            weekly_warning = "Η ημερήσια ζώνη υπερεργασίας είναι προσωρινή: το εβδομαδιαίο σύνολο δεν ξεπερνά τις 40 ώρες"
        summaries.append({"employee_afm": afm, "eponymo": names.get(afm, ("", ""))[0], "onoma": names.get(afm, ("", ""))[1],
                          "contract_kind": contract_kind, "weekly_days": weekly_days,
                          "weekly_days_source": weekly_days_source,
                          "declared": sum(r["declared_minutes"] for r in rows),
                          "actual": sum(r["effective_actual_minutes"] or 0 for r in rows),
                          "extra": sum(r["extra_minutes"] for r in rows),
                          "overwork": overwork, "overtime": overtime, "weekly_warning": weekly_warning})
    summaries.sort(key=lambda r: (r["eponymo"], r["onoma"], r["employee_afm"]))
    return {"days": daily, "employees": summaries,
            "counts": {"all": len(daily), "ok": sum(r["status"] == "ok" for r in daily),
                       "change": sum(r["status"] == "change" for r in daily),
                       "review": sum(r["status"] == "review" for r in daily)}}
