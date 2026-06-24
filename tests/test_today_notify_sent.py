import unittest
from unittest.mock import patch

from app import repo_today_alert


class TodayNotifySentTests(unittest.TestCase):
    @patch("app.repo_today_alert.cursor")
    def test_mark_notify_sent_uses_idempotent_insert(self, mock_cursor):
        ctx = mock_cursor.return_value.__enter__.return_value
        repo_today_alert.mark_notify_sent(
            store_id=3,
            employee_afm="123456789",
            work_date_ergani="24/06/2026",
            notify_kind="late_check_in",
        )
        sql = ctx.execute.call_args[0][0]
        self.assertIn("karta_today_notify_sent", sql)
        self.assertIn("IF NOT EXISTS", sql)


if __name__ == "__main__":
    unittest.main()
