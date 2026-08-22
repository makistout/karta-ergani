from datetime import date
from unittest.mock import patch

from app.repo_employee_leave import (
    load_current_year_normal_leave,
    load_schedule_archive_latest_month,
)


class _Cursor:
    def __init__(self):
        self.params = None

    def execute(self, _sql, params):
        self.params = params

    def fetchall(self):
        return [("111222333", 3), ("999888777", 1)]

    def fetchone(self):
        return (date(2026, 6, 1),)


class _CursorContext:
    def __init__(self, cur):
        self.cur = cur

    def __enter__(self):
        return self.cur

    def __exit__(self, *_args):
        return False


def test_load_current_year_normal_leave_returns_taken_over_entitled():
    cur = _Cursor()
    with patch("app.repo_employee_leave.cursor", return_value=_CursorContext(cur)):
        result = load_current_year_normal_leave(
            store_id=7,
            employee_afms=["999888777", "111222333", "111222333"],
            today=date(2026, 8, 22),
        )

    assert cur.params == [7, "111222333", "999888777", date(2026, 1, 1), date(2026, 8, 22), 2026]
    assert result["111222333"] == {"days_taken": 3}
    assert result["999888777"] == {"days_taken": 1}


def test_load_schedule_archive_latest_month():
    cur = _Cursor()
    with patch("app.repo_employee_leave.cursor", return_value=_CursorContext(cur)):
        result = load_schedule_archive_latest_month(store_id=7)
    assert result == date(2026, 6, 1)
