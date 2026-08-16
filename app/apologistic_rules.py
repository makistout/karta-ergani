"""Pure decision rules for the retrospective schedule engine.

This module deliberately contains no database, Flask or persistence concerns.
Every decision is derived from the current schedule, card and contract facts.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class RuleDecision:
    status: str
    reason: str
    proposed: str
    proposal_basis: str
    rule_id: str


def contract_daily_base_minutes(contract_kind: str, weekly_days: int | None) -> int | None:
    """Return the applicable full-day reference for the selected 5/6-day basis."""
    if weekly_days == 5:
        return 480
    if weekly_days == 6:
        return 400
    return None


def classify_extra_minutes(
    contract_kind: str,
    weekly_days: int | None,
    worked_minutes: int,
    declared_minutes: int,
) -> dict[str, Any]:
    """Classify daily extra time using the contract as the legal reference."""
    overwork = overtime = undeclared = unlawful = 0
    warning = ""
    base = contract_daily_base_minutes(contract_kind, weekly_days)
    if contract_kind == "Πλήρης" and weekly_days == 5:
        overwork = max(0, min(worked_minutes, 540) - 480)
        overtime = max(0, min(worked_minutes - 540, 240))
        unlawful = max(0, worked_minutes - 780)
    elif contract_kind == "Πλήρης" and weekly_days == 6:
        overwork = max(0, min(worked_minutes, 480) - 400)
        overtime = max(0, min(worked_minutes - 480, 240))
        unlawful = max(0, worked_minutes - 720)
    elif contract_kind == "Εκ περιτροπής" and base is not None:
        overtime = max(0, min(worked_minutes - base, 240))
        unlawful = max(0, worked_minutes - base - 240)
        warning = "Χωρίς υπερεργασία· η υπερωρία υπολογίζεται από την ημερήσια βάση της σύμβασης"
    elif contract_kind == "Μερική":
        undeclared = max(0, worked_minutes - declared_minutes)
        warning = "Η μερική απασχόληση δεν παράγει απολογιστική υπερωρία"
    elif worked_minutes > declared_minutes:
        warning = "Άγνωστο καθεστώς· απαιτείται χαρακτηρισμός"
    return {
        "overwork_minutes": overwork,
        "overtime_minutes": overtime,
        "undeclared_extra_minutes": undeclared,
        "unlawful_overtime_minutes": unlawful,
        "classification_warning": warning,
    }


def split_schedule_decision(
    *,
    contract_kind: str,
    daily_base: int | None,
    first_start: int,
    first_end: int,
    second_start: int,
    outside_break: int,
    hm: Callable[[int], str],
) -> RuleDecision:
    if contract_kind != "Πλήρης" or daily_base is None:
        return RuleDecision("review", "Το σπαστό επιτρέπεται μόνο σε πλήρη απασχόληση", "", "Χειροκίνητος έλεγχος", "SPLIT_NON_FULL_REVIEW")
    adjusted_first_end = min(first_end, second_start - 180)
    if adjusted_first_end <= first_start:
        return RuleDecision("review", "Δεν μπορεί να εξασφαλιστεί έγκυρο κενό τριών ωρών", "", "Χειροκίνητος έλεγχος", "SPLIT_INVALID_GAP_REVIEW")
    first_minutes = adjusted_first_end - first_start
    if first_minutes >= daily_base:
        return RuleDecision("review", "Το πρώτο μέρος καλύπτει ήδη ολόκληρη τη συμβατική ημέρα", "", "Έλεγχος πρόσθετης εργασίας/υπερωρίας", "SPLIT_FIRST_PART_EXHAUSTS_DAY")
    second_end = second_start + (daily_base - first_minutes) + outside_break
    proposed = f"{hm(first_start)}–{hm(adjusted_first_end)} · {hm(second_start)}–{hm(second_end)}"
    if adjusted_first_end != first_end:
        return RuleDecision("change", "Το πρώτο μέρος διορθώθηκε ώστε να εξασφαλίζεται διάλειμμα τριών ωρών", proposed, "Κανόνας σπαστού με ελάχιστο κενό 3 ωρών", "SPLIT_GAP_ADJUSTED")
    return RuleDecision("change", "Κατασκευάστηκε σπαστό από τις πραγματικές ενάρξεις και τη συμβατική διάρκεια", proposed, "Υπόλοιπο συμβατικής ημέρας στο δεύτερο μέρος", "SPLIT_REBUILT")


def normal_schedule_decision(
    *,
    contract_kind: str,
    weekly_days: int | None,
    day_state: str,
    declared_label: str,
    declared_minutes: int,
    actual_label: str,
    actual_minutes: int | None,
    effective_actual: int | None,
    declared_start: int | None,
    declared_end: int | None,
    actual_start: int | None,
    actual_end: int | None,
    flex: int,
    outside_break: int,
    has_punch: bool,
    missing_start: bool,
    missing_end: bool,
    unpredictable: bool,
    raw_overnight: bool,
    declared_overnight: bool,
    hm: Callable[[int], str],
) -> RuleDecision:
    base = contract_daily_base_minutes(contract_kind, weekly_days)
    if not has_punch:
        if unpredictable and day_state == "Εργασία":
            return RuleDecision("change", "Μη προβλέψιμο ωράριο χωρίς χτύπημα", "ΜΗ ΕΡΓΑΣΙΑ", "Κανόνας μη προβλέψιμου", "UNPREDICTABLE_NO_PUNCH")
        return RuleDecision("ok", "Δεν υπάρχει χτύπημα· δεν προκύπτει απολογιστική μεταβολή ή υπερωρία", declared_label, "Δηλωμένη κατάσταση", "NO_PUNCH_OK")
    if actual_start is None or actual_end is None or actual_minutes is None:
        return RuleDecision("review", "Δεν προκύπτουν ασφαλή χρονικά όρια από το χτύπημα", actual_label, "Χειροκίνητος έλεγχος", "INVALID_PUNCH_REVIEW")
    if raw_overnight and not declared_overnight and declared_minutes:
        return RuleDecision("review", "Η έξοδος προηγείται της εισόδου χωρίς δηλωμένο νυχτερινό ωράριο", actual_label, "Έλεγχος σειράς χτυπημάτων", "UNDECLARED_OVERNIGHT_REVIEW")
    cap = base or declared_minutes
    if unpredictable:
        duration = min(effective_actual or actual_minutes, cap) if cap else (effective_actual or actual_minutes)
        return RuleDecision("change", "Μη προβλέψιμο ωράριο με πραγματικό χτύπημα", f"{hm(actual_start)}–{hm(actual_start + duration)}", "Πραγματική διάρκεια με συμβατικό κόφτη", "UNPREDICTABLE_PUNCH")
    if day_state == "Τηλεργασία":
        duration = min(effective_actual or actual_minutes, cap) if cap else (effective_actual or actual_minutes)
        return RuleDecision("change", "Τηλεργασία με χτύπημα· εφαρμόζεται μεταβολή όπως στην εργασία", f"{hm(actual_start)}–{hm(actual_start + duration)}", "Διατήρηση κατηγορίας τηλεργασίας", "TELEWORK_WITH_PUNCH")
    if missing_start:
        duration = declared_minutes or base
        if not duration:
            return RuleDecision("review", "Λείπει είσοδος και δεν υπάρχει ασφαλής συμβατική διάρκεια", actual_label, "Χειροκίνητος έλεγχος", "MISSING_ENTRY_NO_DURATION")
        work_end = actual_end - outside_break
        status = "change" if declared_minutes else "review"
        return RuleDecision(status, "Λείπει είσοδος· κατασκευάστηκε από την πραγματική έξοδο", f"{hm(work_end - duration)}–{hm(work_end)}", "Ανάστροφα από την πραγματική λήξη", "MISSING_ENTRY_REBUILT")
    if missing_end:
        duration = declared_minutes or base
        if not duration:
            return RuleDecision("review", "Λείπει έξοδος και δεν υπάρχει ασφαλής συμβατική διάρκεια", actual_label, "Χειροκίνητος έλεγχος", "MISSING_EXIT_NO_DURATION")
        status = "change" if declared_minutes else "review"
        return RuleDecision(status, "Λείπει έξοδος· κατασκευάστηκε από την πραγματική είσοδο", f"{hm(actual_start)}–{hm(actual_start + duration)}", "Συμβατική διάρκεια από την πραγματική έναρξη", "MISSING_EXIT_REBUILT")
    if not declared_minutes:
        duration = min(effective_actual or actual_minutes, cap) if cap else (effective_actual or actual_minutes)
        proposed = f"{hm(actual_start)}–{hm(actual_start + duration)}"
        return RuleDecision("review", "Χτύπημα χωρίς δηλωμένο ωράριο ή σε ημέρα μη εργασίας", proposed, "Πραγματική έναρξη και συμβατική βάση", "UNDECLARED_DAY_PUNCH_REVIEW")
    if contract_kind == "Μερική" and (effective_actual or 0) > declared_minutes:
        duration = min(effective_actual or actual_minutes, cap) if cap else (effective_actual or actual_minutes)
        return RuleDecision("change", "Η πραγματική διάρκεια μερικής υπερβαίνει τη δηλωμένη", f"{hm(actual_start)}–{hm(actual_start + duration)}", "Πραγματική διάρκεια με κόφτη πλήρους ημερήσιας βάσης", "PARTIAL_ACTUAL_CAPPED")
    if declared_start is not None and declared_end is not None:
        arrival_in_flex = declared_start <= actual_start <= declared_start + flex
        acceptable_exit = actual_start > declared_start + flex and actual_end <= declared_end + flex
        if arrival_in_flex or acceptable_exit:
            return RuleDecision("ok", "Η πραγματική απασχόληση βρίσκεται στο αποδεκτό παράθυρο ευελιξίας", declared_label, "Δηλωμένο ωράριο", "FLEX_COMPLIANT")
        if actual_start < declared_start:
            return RuleDecision("change", "Πρόωρη πραγματική έναρξη", f"{hm(actual_start)}–{hm(actual_start + declared_minutes)}", "Πραγματική έναρξη και δηλωμένη διάρκεια", "EARLY_START_SHIFT")
        if actual_minutes <= declared_minutes and actual_end > declared_end + flex:
            work_end = actual_end - outside_break
            return RuleDecision("change", "Καθυστερημένο σύντομο χτύπημα", f"{hm(work_end - declared_minutes)}–{hm(work_end)}", "Ανάστροφα από την πραγματική λήξη", "LATE_SHORT_BACKWARD")
        return RuleDecision("change", "Απόκλιση πραγματικής από δηλωμένη απασχόληση", f"{hm(actual_start)}–{hm(actual_start + declared_minutes)}", "Πραγματική έναρξη και δηλωμένη διάρκεια", "ACTUAL_SHIFTED")
    return RuleDecision("review", "Η περίπτωση δεν καλύπτεται από γνωστό κανόνα", actual_label, "Χειροκίνητος έλεγχος", "UNKNOWN_CASE_REVIEW")
