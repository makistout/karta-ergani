import unittest
from unittest.mock import patch

from app.repo_today_alert import (
    any_deliverable_recipient_not_snoozed,
    is_snoozed,
)


class TodaySnoozePerRecipientTests(unittest.TestCase):
    def test_any_recipient_not_snoozed_when_only_one_snoozed(self):
        with patch(
            "app.repo_notify_recipients.list_deliverable_recipients",
            return_value=[
                {"id": 9, "name": "makis", "telegram_chat_id": "1"},
                {"id": 10, "name": "dimitris", "telegram_chat_id": "2"},
            ],
        ), patch(
            "app.repo_notify_recipients.list_email_deliverable_recipients",
            return_value=[],
        ), patch("app.repo_today_alert.is_snoozed") as snooze:
            snooze.side_effect = lambda **kw: int(kw["recipient_id"]) == 10
            ok = any_deliverable_recipient_not_snoozed(
                store_id=6,
                employee_afm="173705710",
                work_date_ergani="25/06/2026",
                notify_kind="late_check_out",
            )
        self.assertTrue(ok)
        self.assertEqual(snooze.call_count, 1)
        self.assertEqual(snooze.call_args.kwargs["recipient_id"], 9)

    def test_all_recipients_snoozed(self):
        with patch(
            "app.repo_notify_recipients.list_deliverable_recipients",
            return_value=[{"id": 10, "name": "dimitris", "telegram_chat_id": "2"}],
        ), patch(
            "app.repo_notify_recipients.list_email_deliverable_recipients",
            return_value=[],
        ), patch("app.repo_today_alert.is_snoozed", return_value=True):
            ok = any_deliverable_recipient_not_snoozed(
                store_id=6,
                employee_afm="173705710",
                work_date_ergani="25/06/2026",
                notify_kind="late_check_out",
            )
        self.assertFalse(ok)


if __name__ == "__main__":
    unittest.main()
