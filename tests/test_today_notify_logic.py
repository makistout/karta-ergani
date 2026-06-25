import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from app.today_notify_logic import (
    NOTIFY_GRACE_MINUTES,
    notify_auto_send_once,
    resolve_today_notify_kind,
)


class TodayNotifyLogicTests(unittest.TestCase):
    def _athens(self, hour: int, minute: int) -> datetime:
        return datetime(2026, 6, 24, hour, minute, tzinfo=ZoneInfo("Europe/Athens"))

    def test_late_check_in_after_grace_from_schedule_start(self):
        row = {
            "work_date": "24/06/2026",
            "employee_active": True,
            "hour_from": "",
            "hour_to": "",
            "schedule": {"hour_from": "10:00", "hour_to": "16:00"},
        }
        before = resolve_today_notify_kind(row, now=self._athens(10, 9))
        after = resolve_today_notify_kind(row, now=self._athens(10, 10))
        self.assertIsNone(before)
        self.assertEqual(after, "late_check_in")

    def test_future_schedule_start_does_not_wrap_to_late_check_in(self):
        row = {
            "work_date": "24/06/2026",
            "employee_active": True,
            "hour_from": "",
            "hour_to": "",
            "schedule": {"hour_from": "17:00", "hour_to": "01:00"},
        }
        self.assertIsNone(resolve_today_notify_kind(row, now=self._athens(13, 50)))

    def test_late_check_out_after_grace_from_schedule_end(self):
        row = {
            "work_date": "24/06/2026",
            "employee_active": True,
            "hour_from": "10:05",
            "hour_to": "",
            "schedule": {"hour_from": "10:00", "hour_to": "18:30"},
        }
        before = resolve_today_notify_kind(row, now=self._athens(18, 39))
        after = resolve_today_notify_kind(row, now=self._athens(18, 40))
        self.assertIsNone(before)
        self.assertEqual(after, "late_check_out")

    def test_overnight_schedule_end_does_not_wrap_to_late_check_out(self):
        row = {
            "work_date": "24/06/2026",
            "employee_active": True,
            "hour_from": "17:05",
            "hour_to": "",
            "schedule": {"hour_from": "17:00", "hour_to": "01:00"},
        }
        self.assertIsNone(resolve_today_notify_kind(row, now=self._athens(23, 0)))

    def test_future_schedule_end_does_not_wrap_to_late_check_out(self):
        row = {
            "work_date": "24/06/2026",
            "employee_active": True,
            "hour_from": "15:29",
            "hour_to": "",
            "schedule": {"hour_from": "12:00", "hour_to": "20:00"},
        }
        self.assertIsNone(resolve_today_notify_kind(row, now=self._athens(15, 30)))

    def test_missing_exit_8h_when_no_schedule_end(self):
        row = {
            "work_date": "24/06/2026",
            "employee_active": True,
            "hour_from": "08:00",
            "hour_to": "",
            "schedule_label": "—",
        }
        before = resolve_today_notify_kind(row, now=self._athens(15, 59))
        after = resolve_today_notify_kind(row, now=self._athens(16, 0))
        self.assertIsNone(before)
        self.assertEqual(after, "missing_exit_8h")

    def test_grace_constant_is_ten_minutes(self):
        self.assertEqual(NOTIFY_GRACE_MINUTES, 10)

    def test_only_late_check_in_auto_sends_once(self):
        self.assertTrue(notify_auto_send_once("late_check_in"))
        self.assertFalse(notify_auto_send_once("late_check_out"))
        self.assertFalse(notify_auto_send_once("missing_exit_8h"))


if __name__ == "__main__":
    unittest.main()
