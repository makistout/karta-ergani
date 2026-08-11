from datetime import date

import pytest

from app.repo_apologistic import update_proposed


@pytest.mark.parametrize("value", ["κείμενο", "25:00–17:00", "09:70–17:00", "09:00-17:00", ""])
def test_proposal_rejects_non_canonical_time_before_database(value):
    with pytest.raises(ValueError):
        update_proposed(store_id=1, week_from=date(2026, 8, 3), employee_afm="123456789",
                        work_date=date(2026, 8, 4), proposed=value, changed_by="tester")
