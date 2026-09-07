"""Strategies for selecting the daily overwork/overtime basis.

Only the contract strategy is active.  The previous declaration-driven
strategy is deliberately retained here, isolated and covered by tests, so it
can be restored explicitly if the business rule changes again.
"""

from __future__ import annotations


ACTIVE_OVERTIME_BASIS_MODE = "contract"


def contract_overtime_basis(contract_weekly_days: int | None) -> tuple[int | None, str]:
    """Return the daily basis exclusively from the employee contract."""
    if contract_weekly_days in (5, 6):
        return contract_weekly_days, "Σύμβαση εργαζομένου"
    return None, "Μη προσδιορισμένη ημερήσια βάση στη σύμβαση"


def legacy_declared_overtime_basis(
    declared_minutes: int, contract_weekly_days: int | None,
) -> tuple[int | None, str]:
    """Inactive legacy rule: exact declared durations may override the contract."""
    if declared_minutes == 480:
        return 5, "Δηλωμένο ωράριο ημέρας ακριβώς 8:00"
    if declared_minutes == 400:
        return 6, "Δηλωμένο ωράριο ημέρας ακριβώς 6:40"
    return contract_overtime_basis(contract_weekly_days)


def overtime_basis(
    declared_minutes: int, contract_weekly_days: int | None,
) -> tuple[int | None, str]:
    """Dispatch to the explicitly selected strategy."""
    if ACTIVE_OVERTIME_BASIS_MODE == "contract":
        return contract_overtime_basis(contract_weekly_days)
    if ACTIVE_OVERTIME_BASIS_MODE == "legacy_declared":
        return legacy_declared_overtime_basis(declared_minutes, contract_weekly_days)
    raise ValueError(f"Άγνωστη στρατηγική βάσης υπερωρίας: {ACTIVE_OVERTIME_BASIS_MODE}")
