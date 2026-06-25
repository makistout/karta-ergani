import unittest
from unittest.mock import patch

from app import today_alert_notifications


class FakeNotificationLogger:
    def __init__(self):
        self.entries = []

    def info(self, message, **fields):
        self.entries.append(("info", message, fields))

    def error(self, message, **fields):
        self.entries.append(("error", message, fields))


class TodayAlertNotificationPolicyTests(unittest.TestCase):
    def _patch_common(self):
        patches = [
            patch("app.today_alert_notifications.enrich_work_log_rows_with_schedule"),
            patch(
                "app.today_alert_notifications.resolve_today_notify_kind",
                return_value="late_check_in",
            ),
            patch("app.today_alert_notifications.is_snoozed", return_value=False),
            patch("app.today_alert_notifications.is_notify_sent", return_value=False),
            patch("app.today_alert_notifications.list_email_deliverable_recipients", return_value=[]),
            patch("app.today_alert_notifications.ergani_date_to_iso", return_value="2026-06-25"),
            patch("app.telegram_notify.send_telegram_message"),
            patch(
                "app.telegram_notify.format_today_alert_notification",
                return_value="notification",
            ),
        ]
        started = [p.start() for p in patches]
        self.addCleanup(lambda: [p.stop() for p in reversed(patches)])
        return started

    def test_once_policy_sends_then_creates_snooze(self):
        self._patch_common()
        with patch(
            "app.today_alert_notifications.list_deliverable_recipients",
            return_value=[
                {
                    "id": 10,
                    "name": "One",
                    "telegram_chat_id": "123",
                    "notify_repeat_policy": "once_snooze",
                }
            ],
        ), patch("app.today_alert_notifications.mark_notify_sent"), patch(
            "app.today_alert_notifications.create_snooze"
        ) as snooze, patch("app.telegram_notify.send_telegram_message") as send:
            res = today_alert_notifications.send_today_punch_notifications(
                store_id=1,
                store_name="Store",
                employer_afm="123456789",
                branch_aa="0",
                employee_afm="987654321",
                eponymo="Last",
                onoma="First",
                work_date="25/06/2026",
                hour_from=None,
                hour_to=None,
                notify_kind="late_check_in",
                public_base_url="",
                auto_post_sync=True,
            )
        self.assertEqual(res["sent"], 1)
        send.assert_called_once()
        snooze.assert_called_once()
        self.assertEqual(snooze.call_args.kwargs["recipient_id"], 10)

    def test_once_policy_snoozes_each_recipient_after_send(self):
        self._patch_common()
        with patch(
            "app.today_alert_notifications.list_deliverable_recipients",
            return_value=[
                {
                    "id": 9,
                    "name": "makis",
                    "telegram_chat_id": "111",
                    "notify_repeat_policy": "once_snooze",
                },
                {
                    "id": 10,
                    "name": "dimitris",
                    "telegram_chat_id": "222",
                    "notify_repeat_policy": "once_snooze",
                },
            ],
        ), patch("app.today_alert_notifications.mark_notify_sent"), patch(
            "app.today_alert_notifications.create_snooze"
        ) as snooze, patch("app.telegram_notify.send_telegram_message") as send:
            res = today_alert_notifications.send_today_punch_notifications(
                store_id=1,
                store_name="Store",
                employer_afm="123456789",
                branch_aa="0",
                employee_afm="987654321",
                eponymo="Last",
                onoma="First",
                work_date="25/06/2026",
                hour_from=None,
                hour_to=None,
                notify_kind="late_check_in",
                public_base_url="",
                auto_post_sync=True,
            )
        self.assertEqual(res["sent"], 2)
        self.assertEqual(send.call_count, 2)
        self.assertEqual(snooze.call_count, 2)
        snoozed_ids = {c.kwargs["recipient_id"] for c in snooze.call_args_list}
        self.assertEqual(snoozed_ids, {9, 10})

    def test_late_check_in_auto_post_sync_skips_when_already_sent(self):
        self._patch_common()
        with patch(
            "app.today_alert_notifications.is_notify_sent",
            return_value=True,
        ), patch(
            "app.today_alert_notifications.list_deliverable_recipients",
            return_value=[
                {
                    "id": 9,
                    "name": "makis",
                    "telegram_chat_id": "111",
                    "notify_repeat_policy": "once_snooze",
                }
            ],
        ), patch("app.telegram_notify.send_telegram_message") as send:
            res = today_alert_notifications.send_today_punch_notifications(
                store_id=1,
                store_name="Store",
                employer_afm="123456789",
                branch_aa="0",
                employee_afm="987654321",
                eponymo="Last",
                onoma="First",
                work_date="25/06/2026",
                hour_from=None,
                hour_to=None,
                notify_kind="late_check_in",
                public_base_url="",
                auto_post_sync=True,
            )
        self.assertEqual(res["skipped"], "already_sent")
        self.assertEqual(res["sent"], 0)
        send.assert_not_called()

    def test_repeat_policy_sends_without_snooze(self):
        self._patch_common()
        with patch(
            "app.today_alert_notifications.list_deliverable_recipients",
            return_value=[
                {
                    "id": 11,
                    "name": "Repeat",
                    "telegram_chat_id": "456",
                    "notify_repeat_policy": "repeat_until_action",
                }
            ],
        ), patch("app.today_alert_notifications.mark_notify_sent"), patch(
            "app.today_alert_notifications.create_snooze"
        ) as snooze, patch("app.telegram_notify.send_telegram_message") as send:
            res = today_alert_notifications.send_today_punch_notifications(
                store_id=1,
                store_name="Store",
                employer_afm="123456789",
                branch_aa="0",
                employee_afm="987654321",
                eponymo="Last",
                onoma="First",
                work_date="25/06/2026",
                hour_from=None,
                hour_to=None,
                notify_kind="late_check_in",
                public_base_url="",
                auto_post_sync=True,
            )
        self.assertEqual(res["sent"], 1)
        send.assert_called_once()
        snooze.assert_not_called()

    def test_successful_send_logs_recipient_employee_and_channel(self):
        self._patch_common()
        logger = FakeNotificationLogger()
        with patch(
            "app.today_alert_notifications.list_deliverable_recipients",
            return_value=[
                {
                    "id": 12,
                    "name": "Makis",
                    "mobile": "6977392742",
                    "telegram_chat_id": "456",
                    "notify_repeat_policy": "repeat_until_action",
                }
            ],
        ), patch("app.today_alert_notifications.mark_notify_sent"):
            res = today_alert_notifications.send_today_punch_notifications(
                store_id=1,
                store_name="Store",
                employer_afm="123456789",
                branch_aa="0",
                employee_afm="987654321",
                eponymo="Last",
                onoma="First",
                work_date="25/06/2026",
                hour_from=None,
                hour_to=None,
                notify_kind="late_check_in",
                public_base_url="",
                auto_post_sync=True,
                log=logger,
            )
        self.assertEqual(res["sent"], 1)
        send_entries = [
            item for item in logger.entries
            if item[2].get("event") == "today_notification_send"
        ]
        self.assertEqual(len(send_entries), 1)
        fields = send_entries[0][2]
        self.assertEqual(fields["notification_channel"], "telegram")
        self.assertEqual(fields["recipient_name"], "Makis")
        self.assertEqual(fields["recipient_mobile"], "6977392742")
        self.assertEqual(fields["employee_name"], "Last First")
        self.assertEqual(fields["employee_afm"], "987654321")
        self.assertEqual(fields["notify_kind"], "late_check_in")

    def test_post_sync_uses_loaded_schedule_without_second_lookup(self):
        enrich_schedule = self._patch_common()[0]
        with patch(
            "app.today_alert_notifications.list_deliverable_recipients",
            return_value=[
                {
                    "id": 13,
                    "name": "One",
                    "telegram_chat_id": "123",
                    "notify_repeat_policy": "once_snooze",
                }
            ],
        ), patch("app.today_alert_notifications.mark_notify_sent"), patch(
            "app.today_alert_notifications.create_snooze"
        ):
            res = today_alert_notifications.send_today_punch_notifications(
                store_id=1,
                store_name="Store",
                employer_afm="123456789",
                branch_aa="0",
                employee_afm="987654321",
                eponymo="Last",
                onoma="First",
                work_date="25/06/2026",
                hour_from=None,
                hour_to=None,
                notify_kind="late_check_in",
                public_base_url="",
                auto_post_sync=True,
                schedule_loaded=True,
                schedule_hour_from="17:00",
                schedule_hour_to="01:00",
            )
        self.assertEqual(res["sent"], 1)
        enrich_schedule.assert_not_called()


if __name__ == "__main__":
    unittest.main()
