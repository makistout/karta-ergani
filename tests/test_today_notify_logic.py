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
        before = resolve_today_notify_kind(row, now=self._athens(10, 14))
        after = resolve_today_notify_kind(row, now=self._athens(10, 15))
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

    def test_late_check_out_after_grace_from_expected_exit(self):
        row = {
            "work_date": "24/06/2026",
            "employee_active": True,
            "hour_from": "10:05",
            "hour_to": "",
            "schedule": {"hour_from": "10:00", "hour_to": "18:30"},
        }
        # Διάρκεια 8:30 → αναμενόμενη έξοδος 18:35
        before = resolve_today_notify_kind(row, now=self._athens(18, 49))
        after = resolve_today_notify_kind(row, now=self._athens(18, 50))
        self.assertIsNone(before)
        self.assertEqual(after, "late_check_out")

    def test_late_check_out_uses_entry_plus_schedule_duration(self):
        row = {
            "work_date": "24/06/2026",
            "employee_active": True,
            "hour_from": "12:00",
            "hour_to": "",
            "schedule": {"hour_from": "10:00", "hour_to": "18:00"},
        }
        # 8 ώρες από 12:00 → έξοδος 20:00
        at_schedule_end = resolve_today_notify_kind(row, now=self._athens(18, 15))
        after_expected = resolve_today_notify_kind(row, now=self._athens(20, 15))
        self.assertIsNone(at_schedule_end)
        self.assertEqual(after_expected, "late_check_out")

    def test_expected_exit_from_late_entry(self):
        from app.today_notify_logic import expected_exit_from_schedule_and_entry

        self.assertEqual(
            expected_exit_from_schedule_and_entry(
                hour_from="12:00",
                schedule_hour_from="10:00",
                schedule_hour_to="18:00",
            ),
            "20:00",
        )

    def test_overnight_schedule_end_does_not_wrap_to_late_check_out(self):
        row = {
            "work_date": "24/06/2026",
            "employee_active": True,
            "hour_from": "17:05",
            "hour_to": "",
            "schedule": {"hour_from": "17:00", "hour_to": "01:00"},
        }
        self.assertIsNone(resolve_today_notify_kind(row, now=self._athens(23, 0)))

    def test_late_check_out_next_calendar_day_after_overnight_expected_exit(self):
        row = {
            "work_date": "24/06/2026",
            "employee_active": True,
            "hour_from": "17:05",
            "hour_to": "",
            "schedule": {"hour_from": "17:00", "hour_to": "01:00"},
        }
        # Διάρκεια 8 ώρες → αναμενόμενη έξοδος 01:05 (25/06)
        before = resolve_today_notify_kind(
            row,
            now=datetime(2026, 6, 25, 1, 19, tzinfo=ZoneInfo("Europe/Athens")),
        )
        after = resolve_today_notify_kind(
            row,
            now=datetime(2026, 6, 25, 1, 21, tzinfo=ZoneInfo("Europe/Athens")),
        )
        self.assertIsNone(before)
        self.assertEqual(after, "late_check_out")

    def test_late_check_out_when_entry_plus_duration_crosses_midnight(self):
        row = {
            "work_date": "24/06/2026",
            "employee_active": True,
            "hour_from": "22:00",
            "hour_to": "",
            "schedule": {"hour_from": "10:00", "hour_to": "18:00"},
        }
        # 8 ώρες από 22:00 → έξοδος 06:00 (25/06)
        before = resolve_today_notify_kind(
            row,
            now=datetime(2026, 6, 25, 6, 14, tzinfo=ZoneInfo("Europe/Athens")),
        )
        after = resolve_today_notify_kind(
            row,
            now=datetime(2026, 6, 25, 6, 16, tzinfo=ZoneInfo("Europe/Athens")),
        )
        self.assertIsNone(before)
        self.assertEqual(after, "late_check_out")

    def test_expected_exit_reference_date_when_spills_next_day(self):
        from app.today_notify_logic import expected_exit_reference_date_iso

        row = {
            "work_date": "24/06/2026",
            "hour_from": "22:00",
            "schedule": {"hour_from": "10:00", "hour_to": "18:00"},
        }
        self.assertEqual(expected_exit_reference_date_iso(row), "2026-06-25")

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

    def test_grace_constant_is_fifteen_minutes(self):
        self.assertEqual(NOTIFY_GRACE_MINUTES, 15)

    def test_only_late_check_in_auto_sends_once(self):
        self.assertTrue(notify_auto_send_once("late_check_in"))
        self.assertFalse(notify_auto_send_once("late_check_out"))
        self.assertFalse(notify_auto_send_once("missing_exit_8h"))


if __name__ == "__main__":
    unittest.main()
