"""Validated, transient screen adjustments for payroll exports (never identity)."""
from copy import deepcopy
from decimal import Decimal, InvalidOperation

from app.payroll import apply_fmy_to_row, money, payroll_afm_key, recalculate_employee_row


def _number(value):
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        raise ValueError("Μη έγκυρη αριθμητική διόρθωση μισθοδοσίας") from None
    if not number.is_finite() or number < 0 or number > 100000000:
        raise ValueError("Η διόρθωση μισθοδοσίας είναι εκτός ορίων")
    return float(number)


def apply_payroll_adjustments(report, submitted):
    """Use authoritative identities and line types; recompute every derived amount."""
    if not isinstance(submitted, list):
        raise ValueError("Οι διορθώσεις πρέπει να είναι λίστα εργαζομένων")
    result = deepcopy(report)
    by_afm = {payroll_afm_key(row.get("employee_afm")): row for row in result["employees"]}
    seen = set()
    for edit in submitted:
        if not isinstance(edit, dict):
            raise ValueError("Μη έγκυρη διόρθωση εργαζομένου")
        key = payroll_afm_key(edit.get("employee_afm"))
        if key not in by_afm or key in seen:
            raise ValueError("Άγνωστος ή διπλός εργαζόμενος στις διορθώσεις")
        seen.add(key)
        row = by_afm[key]
        if row.get("contract_segments"):
            for field in ("period_salary", "hourly_wage", "legal_hourly", "allowance_base",
                          "children_count", "marital_status", "prior_service_years"):
                if field in edit and edit[field] != row.get(field):
                    raise ValueError("Οι συνολικοί συντελεστές δεν αλλάζουν σε μισθοδοσία με επιμερισμό συμβάσεων")
        for field in ("period_salary", "hourly_wage", "legal_hourly", "allowance_base",
                      "children_count", "prior_service_years", "efka_insurable", "fmy",
                      "salary_payable_days", "salary_unpaid_days"):
            if field in edit and edit[field] is not None:
                row[field] = _number(edit[field])
        if "salary_payable_days" in row:
            days = Decimal(str(row["salary_payable_days"]))
            unpaid = Decimal(str(row.get("salary_unpaid_days") or 0))
            if days > 25 or unpaid > days:
                raise ValueError("Οι ημέρες πρέπει να είναι έως 25 και οι χωρίς αποδοχές έως τις ημέρες μισθοδοσίας")
        for field in ("efka_insurable_manual", "fmy_manual"):
            if field in edit:
                if not isinstance(edit[field], bool):
                    raise ValueError("Μη έγκυρη ένδειξη χειροκίνητης διόρθωσης")
                row[field] = edit[field]
        if "tax_age_group" in edit:
            if edit["tax_age_group"] not in ("under_25", "age_26_30", "over_30"):
                raise ValueError("Μη έγκυρη ηλικιακή ομάδα")
            row["tax_age_group"] = edit["tax_age_group"]
        if "marital_status" in edit:
            if not isinstance(edit["marital_status"], str) or len(edit["marital_status"]) > 20:
                raise ValueError("Μη έγκυρη οικογενειακή κατάσταση")
            row["marital_status"] = edit["marital_status"]
        for collection, identity, fields in (
            ("lines", ("family", "zone", "line_kind", "contract_segment"),
             ("hours", "hourly", "family_percent", "zone_hourly", "zone_percent")),
            ("efka_branches", ("code",), ("employee_percent", "employer_percent")),
        ):
            if collection not in edit:
                continue
            changes = edit[collection]
            original = row.get(collection) or []
            if not isinstance(changes, list) or len(changes) != len(original):
                raise ValueError("Η μισθοδοσία άλλαξε. Ανανεώστε πριν την εξαγωγή")
            for target, change in zip(original, changes):
                if not isinstance(change, dict) or any(target.get(k) != change.get(k) for k in identity):
                    raise ValueError("Οι γραμμές μισθοδοσίας δεν αντιστοιχούν στην περίοδο")
                previous_hourly = target.get("hourly")
                for field in fields:
                    if field in change:
                        target[field] = _number(change[field])
                if collection == "lines" and target.get("line_kind") == "bonus" and target.get("hourly") != previous_hourly:
                    target["formula"] = "Χειροκίνητη διόρθωση: " + str(target["hourly"]) + " €"
        # Preserve explicitly edited branch rates; only tax uses the parameter map.
        updated = recalculate_employee_row(row, period_type=result["period_type"])
        updated = apply_fmy_to_row(updated, result["parameters"], period_type=result["period_type"])
        if updated.get("fmy_manual"):
            updated["tax_formula"] = f"Χειροκίνητη παρακράτηση: {money(updated['fmy']):.2f} €"
        row.update(updated)
    for total, field in (("grand_total", "total"), ("grand_efka_employee", "efka_employee"),
                         ("grand_after_efka", "after_efka"), ("grand_efka_employer", "efka_employer"),
                         ("grand_fmy", "fmy"), ("grand_net", "net"), ("grand_bonuses", "bonuses_total")):
        result[total] = float(money(sum((Decimal(str(r.get(field) or 0)) for r in result["employees"]), Decimal(0))))
    return result
