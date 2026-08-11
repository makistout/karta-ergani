"""Weekly retrospective schedule analysis.

Facts, inferred card boundaries and legal suggestions are kept separately.  A
suggestion is never an automatic Ergani submission; ambiguous cases require
explicit approval.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, time, timedelta
from typing import Any


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
        return f"{start}–{end}"
    if start:
        return f"{start}–"
    return f"–{end}"


def _format_recorded_punches(punches: list[dict[str, Any]]) -> str:
    if not punches:
        return "—"
    return "\n".join(_format_recorded_punch(p) for p in punches)


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
            f"Υπάρχουν {punch_count} εγγραφές σε μη σπαστό ωράριο· για τη διάρκεια χρησιμοποιήθηκε όλο το διάστημα από την πρώτη είσοδο έως την τελευταία έξοδο ({actual_label})."
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
    return " ".join(str(s.get("shift_type") or "").upper() for s in slots)


def _day_state(slots: list[dict[str, Any]]) -> str:
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
    punches: list[dict[str, Any]], slots: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Match one card row per declared part; missing boundaries use declared ones."""
    declared = _working_slots(slots)
    if not declared:
        complete = [p for p in punches if _minutes(p.get("hour_from"), p.get("hour_to")) is not None]
        selected = max(complete, key=lambda p: _minutes(p.get("hour_from"), p.get("hour_to")) or 0) if complete else (punches[0] if punches else None)
        if not selected:
            return [], []
        start = selected.get("hour_from") if _clock(selected.get("hour_from")) else selected.get("hour_to")
        end = selected.get("hour_to") if _clock(selected.get("hour_to")) else selected.get("hour_from")
        return [{"from": start, "to": end,
                 "inferred_from": not bool(_clock(selected.get("hour_from"))),
                 "inferred_to": not bool(_clock(selected.get("hour_to"))),
                 "punch": selected}], []

    if len(declared) == 1 and punches:
        slot = declared[0]
        complete = [p for p in punches if _minutes(p.get("hour_from"), p.get("hour_to")) is not None]
        if complete and len(punches) > 1:
            starts = [(_minute_of_day(p.get("hour_from")), p) for p in punches if _clock(p.get("hour_from"))]
            actual_start, first_punch = min(starts, key=lambda item: item[0])
            boundaries: list[tuple[int, dict[str, Any]]] = []
            for item in punches:
                value = item.get("hour_to") if _clock(item.get("hour_to")) else item.get("hour_from")
                minute = _minute_of_day(value, after=actual_start)
                if minute is not None:
                    boundaries.append((minute, item))
            actual_end, last_punch = max(boundaries, key=lambda item: item[0])
            return [{"from": _hm(actual_start), "to": _hm(actual_end),
                     "inferred_from": False, "inferred_to": False,
                     "punch": first_punch, "slot": slot,
                     "extra_punches": [p for p in punches if p is not first_punch],
                     "envelope_from_multiple": True, "last_punch": last_punch}], []
        pick = complete[0] if complete else min(punches, key=lambda p: _distance(p, slot))
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


def _effective_weekly_days(
    schedule_rows: list[dict[str, Any]], contract_weekly_days: int | None,
) -> tuple[int | None, str]:
    """Infer the week's 5/6-day system from its declarations, then fall back to the contract."""
    declared_by_date: dict[str, int] = defaultdict(int)
    for row in schedule_rows:
        duration = _minutes(row.get("hour_from"), row.get("hour_to"))
        if duration is not None and duration > 0:
            declared_by_date[str(row.get("work_date") or "")] += duration

    declared_days = len(declared_by_date)
    if declared_days >= 6:
        return 6, "Δηλωμένο πρόγραμμα εβδομάδας"
    if declared_days == 5:
        return 5, "Δηλωμένο πρόγραμμα εβδομάδας"

    # Leave/holiday weeks may contain fewer working declarations. In that case
    # the declared daily duration is stronger evidence than the stale contract field.
    durations = list(declared_by_date.values())
    if durations:
        five_day_score = sum(abs(duration - 480) for duration in durations)
        six_day_score = sum(abs(duration - 400) for duration in durations)
        if five_day_score < six_day_score:
            return 5, "Δηλωμένη ημερήσια διάρκεια εβδομάδας"
        if six_day_score < five_day_score:
            return 6, "Δηλωμένη ημερήσια διάρκεια εβδομάδας"
    return contract_weekly_days, "Τρέχουσα σύμβαση"


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
    """Daily declaration bands. Weekly/arrangement legality remains a warning."""
    overwork = overtime = undeclared = unlawful = 0
    warning = ""
    if contract_kind == "Πλήρης" and weekly_days == 5:
        overwork = max(0, min(worked, 540) - 480)
        overtime = max(0, min(worked - 540, 240))
        unlawful = max(0, worked - 780)
    elif contract_kind == "Πλήρης" and weekly_days == 6:
        overwork = max(0, min(worked, 480) - 400)
        overtime = max(0, min(worked - 480, 240))
        unlawful = max(0, worked - 720)
    elif contract_kind == "Εκ περιτροπής":
        overtime = max(0, min(worked - declared, 240))
        unlawful = max(0, worked - declared - 240)
        warning = "Χωρίς υπερεργασία· το ακριβές όριο εξαρτάται από τη δηλωμένη κατανομή"
    elif contract_kind == "Μερική":
        undeclared = max(0, worked - declared)
        warning = "Δεν παράγεται δήλωση υπερωρίας μερικής απασχόλησης"
    elif worked > declared:
        warning = "Άγνωστο καθεστώς· απαιτείται χαρακτηρισμός"
    return {"overwork_minutes": overwork, "overtime_minutes": overtime,
            "undeclared_extra_minutes": undeclared, "unlawful_overtime_minutes": unlawful,
            "classification_warning": warning}


def _proposed_normal_slot(
    ds: int, de: int, ps: int, pe: int, declared_minutes: int,
    outside_break: int, flex: int, actual_minutes: int,
) -> tuple[int, int, str]:
    if actual_minutes <= declared_minutes and pe > de + flex:
        # Suspected late/missed entry: anchor backwards from the real exit.
        return pe - declared_minutes - outside_break, pe, "Ανάστροφα από την πραγματική λήξη"
    return ps, ps + declared_minutes + outside_break, "Από την πραγματική έναρξη"


def _overtime_segments(work_date: str, start: int | None, end: int | None) -> list[dict[str, Any]]:
    """Split overtime by calendar day because each part is submitted on the day it occurs."""
    if start is None or end is None or end <= start:
        return []
    base = datetime.strptime(work_date, "%d/%m/%Y").date()
    segments: list[dict[str, Any]] = []
    cursor = start
    while cursor < end:
        day_index = cursor // 1440
        boundary = (day_index + 1) * 1440
        segment_end = min(end, boundary)
        segment_date = base + timedelta(days=day_index)
        segments.append({"date": segment_date.strftime("%d/%m/%Y"), "from": _hm(cursor),
                         "to": _hm(segment_end), "minutes": segment_end - cursor})
        cursor = segment_end
    return segments


def build_weekly_report(
    schedule_rows: list[dict[str, Any]], work_rows: list[dict[str, Any]], contracts: list[dict[str, Any]],
) -> dict[str, Any]:
    schedules: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    punches: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    contracts_by_afm = {str(r.get("employee_afm") or "").zfill(9): r for r in contracts}
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
            })
    for rows in missing_declared_by_afm.values():
        rows.sort(key=lambda item: datetime.strptime(item["work_date"], "%d/%m/%Y"))

    daily: list[dict[str, Any]] = []
    for afm, work_date in sorted(set(schedules) | set(punches), key=lambda k: (datetime.strptime(k[1], "%d/%m/%Y"), names.get(k[0], ("", "")), k[0])):
        slots, day_punches = schedules.get((afm, work_date), []), punches.get((afm, work_date), [])
        work_slots = _working_slots(slots)
        matched, orphan_punches = _match_punches(day_punches, slots)
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
        contract = contracts_by_afm.get(afm)
        contract_kind, _contract_weekly_days = _contract_kind(contract)
        weekly_days, weekly_days_source = weekly_system_by_afm.get(
            afm, (_contract_weekly_days, "Τρέχουσα σύμβαση")
        )
        contract_flags = _contract_flags(contract)
        declared_minutes = sum(_minutes(s.get("hour_from"), s.get("hour_to")) or 0 for s in work_slots)
        actual_minutes = sum(_minutes(m.get("from"), m.get("to")) or 0 for m in matched) if matched else None
        inferred = any(m.get("inferred_from") or m.get("inferred_to") for m in matched)
        declared_label = " · ".join(f"{s.get('hour_from')}–{s.get('hour_to')}" for s in work_slots) or (str(slots[0].get("shift_type") or "") if slots else "—")
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
        start_difference = ps - ds if ps is not None and ds is not None else None
        end_difference = pe - de if pe is not None and de is not None else None
        bands = _classify_extra(contract_kind, weekly_days, effective_actual or 0, declared_minutes)
        if contract_flags["work_arrangement"]:
            bands["classification_warning"] = "Διευθέτηση χρόνου εργασίας: απαιτείται έλεγχος περιόδου αναφοράς και ορίου 10 ωρών"
        elif contract_flags["uneven_distribution"]:
            bands["classification_warning"] = "Ανισομερής κατανομή: απαιτείται επιβεβαίωση της νόμιμης βάσης και του εβδομαδιαίου συνόλου"

        status, reason, proposed, proposal_basis = "ok", "Δεν απαιτείται μεταβολή", declared_label, "Δηλωμένο ωράριο"
        state = _day_state(slots)
        replacement_candidates: list[dict[str, Any]] = []
        weekly_punch_details: list[dict[str, Any]] = []
        weekly_punch_days: int | None = None
        contract_required_days: int | None = _contract_weekly_days
        special_non_work_punch = bool(matched and state in ("Μη εργασία", "Ρεπό") and day_punches)
        if matched and (not slots or _is_non_work(slots)) and day_punches:
            normal_limit = 480 if weekly_days == 5 else 400 if weekly_days == 6 else None
            if (contract_kind == "Πλήρης" and normal_limit is not None
                    and (effective_actual or 0) > normal_limit and ps is not None and pe is not None):
                normal_work = min(effective_actual or 0, normal_limit)
                proposed = f"{_hm(ps)}–{_hm(ps + normal_work + outside_break)}"
                proposal_basis = f"Όριο κανονικής εργασίας πλήρους {weekly_days}ημέρου ({_hm(normal_limit)})"
                status = "change"
                reason = (
                    f"Εργασία σε ημέρα μη εργασίας: προτείνεται μόνο η κανονική {normal_limit // 60}:"
                    f"{normal_limit % 60:02d} διάρκεια· η υπερεργασία δεν δηλώνεται και η υπερωρία υποβάλλεται χωριστά"
                )
            else:
                status, reason, proposed = "review", "Χτύπημα χωρίς ωράριο ή σε ημέρα μη εργασίας", actual_label
            if special_non_work_punch:
                weekly_punch_days = len(punch_dates_by_afm.get(afm, set()))
                weekly_punch_details = list(weekly_punch_details_by_afm.get(afm, []))
                if contract_required_days and weekly_punch_days >= contract_required_days:
                    status = "ok"
                    reason = (
                        f"Χτύπημα σε {state}: οι {weekly_punch_days} ημέρες με κάρτα καλύπτουν "
                        f"τις {contract_required_days} ημέρες της σύμβασης"
                    )
                else:
                    status = "review"
                    replacement_candidates = list(missing_declared_by_afm.get(afm, []))
                    required_label = str(contract_required_days) if contract_required_days else "άγνωστες"
                    reason = (
                        f"Χτύπημα σε {state}: {weekly_punch_days} ημέρες με κάρτα έναντι "
                        f"{required_label} ημερών σύμβασης· απαιτείται επιλογή ημέρας αντικατάστασης"
                    )
        elif work_slots and fully_missing:
            status, reason, proposed = "ok", "Δεν υπάρχει χτύπημα· δεν προκύπτει απολογιστική μεταβολή ή υπερωρία", declared_label
        elif work_slots and matched:
            arrival_in_flex = bool(ds is not None and ps is not None and ds <= ps <= ds + flex)
            has_declarable_extra = bands["overtime_minutes"] > 0
            if orphan_punches and len(work_slots) == 1:
                status, reason = "review", "Υπάρχουν επιπλέον ορφανές εγγραφές χτυπημάτων"
            elif len(work_slots) > 1:
                changed_parts = []
                for item, slot in zip(matched, work_slots):
                    sf = _minute_of_day(slot.get("hour_from")) or 0
                    st = _minute_of_day(slot.get("hour_to"), after=sf) or sf
                    pf = _minute_of_day(item.get("from")) or sf
                    pt = _minute_of_day(item.get("to"), after=pf) or st
                    duration = _minutes(slot.get("hour_from"), slot.get("hour_to")) or 0
                    changed_parts.append(f"{_hm(pf)}–{_hm(pf + duration)}" if (pf != sf or pt != st) else f"{_hm(sf)}–{_hm(st)}")
                proposed = " · ".join(changed_parts)
                if inferred or orphan_punches:
                    status, reason = "review", "Σπαστό ωράριο με τεκμαρτό ή ορφανό χτύπημα"
                elif proposed != declared_label:
                    status, reason = "change", "Απόκλιση σε τμήμα σπαστού ωραρίου"
            elif inferred:
                if ps != ds or pe != de or has_declarable_extra:
                    status, reason = "change", "Ελλιπές χτύπημα συμπληρώθηκε από το δηλωμένο όριο"
                else:
                    reason = "Ελλιπές χτύπημα· χρησιμοποιήθηκε το δηλωμένο όριο"
            elif arrival_in_flex:
                if has_declarable_extra:
                    status, reason = "change", "Η κανονική βάρδια μένει δηλωμένη· απαιτείται απολογιστική υπερωρία"
                else:
                    reason = "Έναρξη εντός ευέλικτης προσέλευσης"
            elif ps is not None and pe is not None and ds is not None and de is not None:
                start, end, proposal_basis = _proposed_normal_slot(ds, de, ps, pe, declared_minutes, outside_break, flex, actual_minutes or 0)
                proposed = f"{_hm(start)}–{_hm(end)}"
                status, reason = "change", "Απόκλιση πραγματικής από δηλωμένη απασχόληση"

        overtime_from = overtime_to = None
        if bands["overtime_minutes"] and ps is not None and pe is not None:
            threshold = 540 if contract_kind == "Πλήρης" and weekly_days == 5 else 480 if contract_kind == "Πλήρης" and weekly_days == 6 else declared_minutes
            overtime_from = ps + outside_break + threshold
            overtime_to = min(pe, overtime_from + bands["overtime_minutes"])
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
            single_schedule=len(work_slots) == 1, overtime_segments=overtime_segments,
            corrected_extra_punches=corrected_extra_punches,
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
            if contract_required_days and (weekly_punch_days or 0) >= contract_required_days:
                status_explanation.append("Οι ημέρες με κάρτα καλύπτουν ή υπερβαίνουν τις ημέρες σύμβασης, επομένως η συγκεκριμένη ημέρα χαρακτηρίζεται Σύμφωνο.")
            elif replacement_candidates:
                status_explanation.append("Δηλωμένες ημέρες εργασίας χωρίς χτύπημα που μπορούν να εξεταστούν για αντικατάσταση:")
                status_explanation.extend(f"  · {item['work_date']}: {item['declared']}" for item in replacement_candidates)
            else:
                status_explanation.append("Δεν βρέθηκε δηλωμένη ημέρα εργασίας χωρίς χτύπημα ως υποψήφια αντικατάστασης.")
        daily.append({
            "employee_afm": afm, "eponymo": names.get(afm, ("", ""))[0], "onoma": names.get(afm, ("", ""))[1],
            "work_date": work_date, "contract_kind": contract_kind, "weekly_days": weekly_days,
            "weekly_days_source": weekly_days_source,
            **contract_flags,
            "declared": declared_label, "punch_recorded": punch_recorded,
            "actual": actual_label, "proposed": proposed,
            "proposal_basis": proposal_basis, "status": status, "reason": reason,
            "status_explanation": status_explanation, "orphan_punches": orphan_details,
            "corrected_extra_punches": [{k: v for k, v in item.items() if k != "recorded"}
                                         for item in corrected_extra_punches],
            "declared_minutes": declared_minutes, "actual_minutes": actual_minutes,
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
            "weekly_punch_details": weekly_punch_details,
        })

    # If seven workdays were declared and one has no card, propose (never auto-apply) rest.
    by_employee: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in daily:
        by_employee[row["employee_afm"]].append(row)
    for rows in by_employee.values():
        declared_workdays = [r for r in rows if r["declared_minutes"] > 0]
        if len(declared_workdays) == 7:
            for row in declared_workdays:
                if row["punch_count"] == 0:
                    rest_reason = "Εβδομάδα 7 δηλωμένων ημερών χωρίς χτύπημα: πρόταση ρεπό με έγκριση"
                    row.update(status="review", reason=rest_reason,
                               proposed="ΑΝΑΠΑΥΣΗ/ΡΕΠΟ", suggested_rest=True,
                               requires_confirmation=True, confidence="Χαμηλή",
                               status_explanation=["Αποτέλεσμα: Έλεγχος", rest_reason,
                                                   "Δεν υπάρχει καμία εγγραφή χτυπήματος στην κάρτα.",
                                                   "Πρόταση: ΑΝΑΠΑΥΣΗ/ΡΕΠΟ (μόνο με έγκριση).",
                                                   "Βεβαιότητα: Χαμηλή.", "Χρειάζεται επιβεβαίωση πριν από οποιαδήποτε δήλωση."])

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
