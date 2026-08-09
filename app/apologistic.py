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
        return [{"from": selected.get("hour_from"), "to": selected.get("hour_to"),
                 "inferred_from": False, "inferred_to": False, "punch": selected}], []

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


def _break_context(contract: dict[str, Any] | None, work_slots: list[dict[str, Any]]) -> tuple[int, int | None, int]:
    raw = (contract or {}).get("break_minutes")
    if raw is None and work_slots:
        raw = work_slots[0].get("break_minutes")
    minutes = max(0, int(raw or 0))
    in_work = (contract or {}).get("break_in_work")
    if in_work is None and work_slots:
        in_work = work_slots[0].get("break_in_work")
    # Blank is not silently treated as outside: it needs confirmation.
    outside = minutes if work_slots and in_work == 0 else 0
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

    daily: list[dict[str, Any]] = []
    for afm, work_date in sorted(set(schedules) | set(punches), key=lambda k: (datetime.strptime(k[1], "%d/%m/%Y"), names.get(k[0], ("", "")), k[0])):
        slots, day_punches = schedules.get((afm, work_date), []), punches.get((afm, work_date), [])
        work_slots = _working_slots(slots)
        matched, orphan_punches = _match_punches(day_punches, slots)
        contract = contracts_by_afm.get(afm)
        contract_kind, weekly_days = _contract_kind(contract)
        contract_flags = _contract_flags(contract)
        declared_minutes = sum(_minutes(s.get("hour_from"), s.get("hour_to")) or 0 for s in work_slots)
        actual_minutes = sum(_minutes(m.get("from"), m.get("to")) or 0 for m in matched) if matched else None
        inferred = any(m.get("inferred_from") or m.get("inferred_to") for m in matched)
        fully_missing = bool(work_slots and not day_punches)
        declared_label = " · ".join(f"{s.get('hour_from')}–{s.get('hour_to')}" for s in work_slots) or (str(slots[0].get("shift_type") or "") if slots else "—")
        actual_label = " · ".join(f"{m.get('from') or '—'}–{m.get('to') or '—'}" for m in matched) or "—"
        flex = int((contract or {}).get("flex_arrival_minutes") or (work_slots[0].get("flex_arrival_minutes") if work_slots else 0) or 0)
        break_minutes, break_in_work, outside_break = _break_context(contract, work_slots)
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
        if matched and (not slots or _is_non_work(slots)) and day_punches:
            status, reason, proposed = "review", "Χτύπημα χωρίς ωράριο ή σε ημέρα μη εργασίας", actual_label
        elif work_slots and fully_missing:
            status, reason, proposed = "review", "Δεν υπάρχει χτύπημα· τεκμαίρεται το δηλωμένο ωράριο", declared_label
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
        requires_confirmation = (status != "ok" or contract_kind in ("Άγνωστη σύμβαση", "Μη προσδιορισμένη")
                                 or break_in_work is None and break_minutes > 0
                                 or contract_flags["work_arrangement"] or contract_flags["uneven_distribution"])
        confidence = "Χαμηλή" if requires_confirmation else ("Μέση" if len(day_punches) > len(work_slots) else "Υψηλή")
        daily.append({
            "employee_afm": afm, "eponymo": names.get(afm, ("", ""))[0], "onoma": names.get(afm, ("", ""))[1],
            "work_date": work_date, "contract_kind": contract_kind, "weekly_days": weekly_days,
            **contract_flags,
            "declared": declared_label, "actual": actual_label, "proposed": proposed,
            "proposal_basis": proposal_basis, "status": status, "reason": reason,
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
            "overnight": bool(first and _minutes(first.get("from"), first.get("to")) is not None and (_minute_of_day(first.get("to")) or 0) < (_minute_of_day(first.get("from")) or 0)),
            "requires_confirmation": requires_confirmation, "confidence": confidence,
            "sixth_day_candidate": False, "suggested_rest": False,
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
                    row.update(status="review", reason="Εβδομάδα 7 δηλωμένων ημερών χωρίς χτύπημα: πρόταση ρεπό με έγκριση",
                               proposed="ΑΝΑΠΑΥΣΗ/ΡΕΠΟ", suggested_rest=True,
                               requires_confirmation=True, confidence="Χαμηλή")

    summaries = []
    for afm, rows in by_employee.items():
        overwork = sum(r["overwork_minutes"] for r in rows)
        overtime = sum(r["overtime_minutes"] for r in rows)
        contract_kind, weekly_days = _contract_kind(contracts_by_afm.get(afm))
        weekly_warning = ""
        cap = 300 if weekly_days == 5 else 480 if weekly_days == 6 else None
        if cap is not None and overwork > cap:
            weekly_warning = "Υπέρβαση εβδομαδιαίου ορίου υπερεργασίας"
        elif overwork and sum(r["effective_actual_minutes"] or 0 for r in rows) <= 2400:
            weekly_warning = "Η ημερήσια ζώνη υπερεργασίας είναι προσωρινή: το εβδομαδιαίο σύνολο δεν ξεπερνά τις 40 ώρες"
        summaries.append({"employee_afm": afm, "eponymo": names.get(afm, ("", ""))[0], "onoma": names.get(afm, ("", ""))[1],
                          "contract_kind": contract_kind, "weekly_days": weekly_days,
                          "declared": sum(r["declared_minutes"] for r in rows),
                          "actual": sum(r["effective_actual_minutes"] or 0 for r in rows),
                          "extra": sum(r["extra_minutes"] for r in rows),
                          "overwork": overwork, "overtime": overtime, "weekly_warning": weekly_warning})
    summaries.sort(key=lambda r: (r["eponymo"], r["onoma"], r["employee_afm"]))
    return {"days": daily, "employees": summaries,
            "counts": {"all": len(daily), "ok": sum(r["status"] == "ok" for r in daily),
                       "change": sum(r["status"] == "change" for r in daily),
                       "review": sum(r["status"] == "review" for r in daily)}}
