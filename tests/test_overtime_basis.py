from app.overtime_basis import (
    ACTIVE_OVERTIME_BASIS_MODE,
    legacy_declared_overtime_basis,
    overtime_basis,
)


def test_active_overtime_basis_is_contract_only():
    assert ACTIVE_OVERTIME_BASIS_MODE == "contract"
    assert overtime_basis(480, 6) == (6, "Σύμβαση εργαζομένου")
    assert overtime_basis(400, 5) == (5, "Σύμβαση εργαζομένου")


def test_inactive_legacy_strategy_is_retained_for_explicit_future_activation():
    assert legacy_declared_overtime_basis(480, 6)[0] == 5
    assert legacy_declared_overtime_basis(400, 5)[0] == 6
