import unittest
from unittest.mock import patch

from app import scheduled_sync
from app import scheduled_sync_notifications
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

    def test_skip_summary_explains_exact_reason(self):
        summary = scheduled_sync_notifications._skip_summary(
            {"already_sent": 4, "card_already_punched": 1}
        )
        self.assertIn("4 ήδη στάλθηκε αυτόματη ειδοποίηση σήμερα", summary)
        self.assertIn("1 υπάρχει ήδη αντίστοιχο χτύπημα κάρτας", summary)

    def test_after_card_sync_is_disabled(self):
        cfg = {
            "id": 7,
            "name": "Demo",
            "employer_afm": "123456789",
            "branch_aa": "0",
            "username": "portal-user",
            "password": "portal-pass",
        }
        with (
            patch("app.scheduled_sync.threading.Thread") as thread,
            patch("app.scheduled_sync.time.sleep") as sleep,
            patch("app.scheduled_sync.sync_work_log_from_portal") as work_log_sync,
        ):
            self.assertFalse(
                scheduled_sync.enqueue_sync_store_today_after_card(
                    cfg,
                    work_date_iso="2026-06-29",
                )
            )

        thread.assert_not_called()
        sleep.assert_not_called()
        work_log_sync.assert_not_called()

    def test_after_login_sync_enqueues_store_scope_once(self):
        class ImmediateThread:
            def __init__(self, target, **kwargs):
                self.target = target

            def start(self):
                self.target()

        scheduled_sync._after_login_sync_seen.clear()
        with (
            patch("app.scheduled_sync.threading.Thread", ImmediateThread),
            patch("app.scheduled_sync.run_scheduled_sync") as run_sync,
        ):
            self.assertTrue(
                scheduled_sync.enqueue_sync_allowed_stores_after_login(
                    user_id=42,
                    store_ids=[9, 7, 7],
                )
            )
            self.assertFalse(
                scheduled_sync.enqueue_sync_allowed_stores_after_login(
                    user_id=42,
                    store_ids=[7, 9],
                )
            )

        run_sync.assert_called_once_with(store_ids=[7, 9], skip_if_running=True)

    def test_after_login_sync_super_admin_uses_all_stores(self):
        class ImmediateThread:
            def __init__(self, target, **kwargs):
                self.target = target

            def start(self):
                self.target()

        scheduled_sync._after_login_sync_seen.clear()
        with (
            patch("app.scheduled_sync.threading.Thread", ImmediateThread),
            patch("app.scheduled_sync.run_scheduled_sync") as run_sync,
        ):
            self.assertTrue(
                scheduled_sync.enqueue_sync_allowed_stores_after_login(
                    user_id=1,
                    store_ids=None,
                )
            )

        run_sync.assert_called_once_with(store_ids=None, skip_if_running=True)


if __name__ == "__main__":
    unittest.main()
