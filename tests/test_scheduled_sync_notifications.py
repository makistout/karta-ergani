import unittest

from app import scheduled_sync
from config import Config


class ScheduledSyncNotificationTests(unittest.TestCase):
    def test_post_sync_notify_key_uses_store_and_date(self):
        self.assertEqual(
            scheduled_sync._post_sync_notify_key(7, "2026-06-24T12:00:00"),
            "7|2026-06-24",
        )

    def test_enqueue_post_sync_notifications_respects_feature_flag(self):
        old = Config.KARTA_POST_SYNC_NOTIFY_ENABLED
        Config.KARTA_POST_SYNC_NOTIFY_ENABLED = False
        try:
            enqueued = scheduled_sync.enqueue_post_sync_notifications(
                {"id": 1, "name": "Demo"},
                work_date_iso=scheduled_sync._today_iso(),
                parent_run_id="test",
            )
            self.assertFalse(enqueued)
        finally:
            Config.KARTA_POST_SYNC_NOTIFY_ENABLED = old

    def test_enqueue_post_sync_notifications_skips_non_today_date(self):
        old = Config.KARTA_POST_SYNC_NOTIFY_ENABLED
        Config.KARTA_POST_SYNC_NOTIFY_ENABLED = True
        try:
            enqueued = scheduled_sync.enqueue_post_sync_notifications(
                {
                    "id": 1,
                    "name": "Demo",
                    "employer_afm": "123456789",
                    "username": "user",
                    "password": "pass",
                },
                work_date_iso="2000-01-01",
                parent_run_id="test",
            )
            self.assertFalse(enqueued)
        finally:
            Config.KARTA_POST_SYNC_NOTIFY_ENABLED = old


if __name__ == "__main__":
    unittest.main()
