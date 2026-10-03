from datetime import date
from unittest.mock import patch

from app.telegram_assistant_service import validate_and_describe
from app.leave_balance import (
    annual_normal_leave_entitlement,
    is_normal_leave_type,
    normal_leave_block_message,
    normal_leave_block_reason,
)


def test_is_normal_leave_type_accepts_code_and_label():
    assert is_normal_leave_type("ADKAN") is True
    assert is_normal_leave_type("κανονική") is True
    assert is_normal_leave_type("Κανονική άδεια") is True
    assert is_normal_leave_type("ADAS") is False
    assert is_normal_leave_type("") is False


def test_entitlement_follows_weekly_days():
    assert annual_normal_leave_entitlement({"weekly_work_days": "5"}) == 22
    assert annual_normal_leave_entitlement({"weekly_work_days": "6ημερο"}) == 26
    assert annual_normal_leave_entitlement({}) is None


def test_block_message_uses_taken_over_entitled():
    assert normal_leave_block_message(
        employee_name="ΠΑΠΑΔΟΠΟΥΛΟΣ ΓΙΩΡΓΟΣ", days_taken=22, days_entitled=22,
    ) == (
        "Ο εργαζόμενος ΠΑΠΑΔΟΠΟΥΛΟΣ ΓΙΩΡΓΟΣ έχει ήδη 22/22 μέρες "
        "κανονικής άδειας και δεν μπορεί να προστεθεί άλλη μέρα"
    )


def test_normal_leave_blocks_when_taken_reaches_entitlement():
    with (
        patch("app.leave_balance.list_current_for_store", return_value=[{
            "employee_afm": "111222333", "weekly_work_days": "5",
        }]),
        patch("app.leave_balance.normal_leave_used_days", return_value=22),
    ):
        reason = normal_leave_block_reason(
            store_id=4,
            employer_afm="123456789",
            branch_aa="0",
            employee_afm="111222333",
            employee_name="HOXHA DASHURI",
            leave_type="κανονική",
            leave_date="2026-10-03",
        )
    assert reason == (
        "Ο εργαζόμενος HOXHA DASHURI έχει ήδη 22/22 μέρες "
        "κανονικής άδειας και δεν μπορεί να προστεθεί άλλη μέρα"
    )


def test_normal_leave_allows_when_one_day_remains():
    with (
        patch("app.leave_balance.list_current_for_store", return_value=[{
            "employee_afm": "111222333", "weekly_work_days": "5",
        }]),
        patch("app.leave_balance.normal_leave_used_days", return_value=21),
    ):
        assert normal_leave_block_reason(
            store_id=4,
            employer_afm="123456789",
            branch_aa="0",
            employee_afm="111222333",
            employee_name="HOXHA DASHURI",
            leave_type="ADKAN",
            leave_date=date(2026, 10, 3),
        ) is None


def test_normal_leave_counts_pending_days_from_same_batch():
    with (
        patch("app.leave_balance.list_current_for_store", return_value=[{
            "employee_afm": "111222333", "weekly_work_days": "5",
        }]),
        patch("app.leave_balance.normal_leave_used_days", return_value=21),
    ):
        reason = normal_leave_block_reason(
            store_id=4,
            employer_afm="123456789",
            branch_aa="0",
            employee_afm="111222333",
            employee_name="HOXHA DASHURI",
            leave_type="Κανονική άδεια",
            leave_date="2026-10-04",
            extra_pending_days=1,
        )
    assert "21/22" not in (reason or "")
    assert "22/22" in (reason or "")


def test_assistant_blocks_normal_leave_when_balance_is_full():
    parsed = {
        "intent": "leave",
        "store_id": 4,
        "employee_afms": ["111222333"],
        "date": "2026-10-03",
        "leave_type": "κανονική",
        "confidence": 0.99,
    }
    with patch(
        "app.leave_balance.normal_leave_block_reason",
        return_value=(
            "Ο εργαζόμενος HOXHA DASHURI έχει ήδη 22/22 μέρες "
            "κανονικής άδειας και δεν μπορεί να προστεθεί άλλη μέρα"
        ),
    ):
        status, validation, _proposed = validate_and_describe(
            parsed,
            contexts=[{"store_id": 4, "store_name": "ERATO", "employer_afm": "123456789", "branch_aa": "0"}],
            employees=[{"store_id": 4, "afm": "111222333", "name": "HOXHA DASHURI"}],
            user_text="Άδεια κανονική στον Hoxha αύριο",
        )
    assert status == "needs_clarification"
    assert any("22/22" in item and "δεν μπορεί να προστεθεί" in item for item in validation["errors"])


def test_other_leave_types_are_not_checked():
    assert normal_leave_block_reason(
        store_id=4,
        employer_afm="123456789",
        branch_aa="0",
        employee_afm="111222333",
        employee_name="HOXHA DASHURI",
        leave_type="ADAS",
        leave_date="2026-10-03",
    ) is None
