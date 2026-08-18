from datetime import date

import pytest

from app.repo_apologistic import update_proposed


@pytest.mark.parametrize("value", ["κείμενο", "25:00–17:00", "09:70–17:00", "09:00-17:00", "", "ΤΗΛΕΡΓΑΣΙΑ"])
def test_proposal_rejects_non_canonical_time_before_database(value):
    with pytest.raises(ValueError):
        update_proposed(store_id=1, week_from=date(2026, 8, 3), employee_afm="123456789",
                        work_date=date(2026, 8, 4), proposed=value, changed_by="tester")


@pytest.mark.parametrize("value,expected", [
    ("ΑΝΑΠΑΥΣΗ/ΡΕΠΟ", "ΑΝΑΠΑΥΣΗ/ΡΕΠΟ"),
    ("ΡΕΠΟ", "ΑΝΑΠΑΥΣΗ/ΡΕΠΟ"),
    ("ΜΗ ΕΡΓΑΣΙΑ", "ΜΗ ΕΡΓΑΣΙΑ"),
    ("ΤΗΛΕΡΓΑΣΙΑ 09:00–17:00", "ΤΗΛΕΡΓΑΣΙΑ 09:00–17:00"),
    ("09:00–17:00", "09:00–17:00"),
    ("09:00–13:00 · 17:00–21:00", "09:00–13:00 · 17:00–21:00"),
    ("ΑΔΕΙΑ ADKAN", "ΑΔΕΙΑ ADKAN"),
    ("ADAA", "ΑΔΕΙΑ ADAA"),
])
def test_normalize_proposed_value_accepts_labels_and_hours(value, expected):
    from app.repo_apologistic import normalize_proposed_value
    assert normalize_proposed_value(value) == expected
