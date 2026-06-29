import unittest
from unittest.mock import Mock, patch

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

    def test_after_card_sync_refreshes_only_work_log(self):
        class ImmediateThread:
            def __init__(self, target, **kwargs):
                self.target = target

            def start(self):
                self.target()

        fake_logger = Mock()
        fake_logger.info = Mock()
        fake_logger.warning = Mock()
        fake_logger.error = Mock()

        cfg = {
            "id": 7,
            "name": "Demo",
            "employer_afm": "123456789",
            "branch_aa": "0",
            "username": "portal-user",
            "password": "portal-pass",
        }
        ctx = {**cfg, "api_base_url": "https://ergani.example"}

        with (
            patch("app.scheduled_sync.threading.Thread", ImmediateThread),
            patch("app.scheduled_sync.store_api_context", return_value=ctx),
            patch("app.scheduled_sync.KartaLogger", return_value=fake_logger),
            patch("app.scheduled_sync.sync_schedule_from_portal") as schedule_sync,
            patch(
                "app.scheduled_sync.sync_work_log_from_portal",
                return_value={"success": True, "count": 3, "detail": "ok"},
            ) as work_log_sync,
            patch(
                "app.scheduled_sync.repo_store.get_store_config",
                return_value={"work_log_last_sync_at": "2026-06-29T10:00:00"},
            ),
            patch("app.scheduled_sync._finish_store_run") as finish_run,
        ):
            self.assertTrue(
                scheduled_sync.enqueue_sync_store_today_after_card(
                    cfg,
                    work_date_iso="2026-06-29",
                )
            )

        schedule_sync.assert_not_called()
        work_log_sync.assert_called_once_with(
            ctx,
            from_iso="2026-06-29",
            to_iso="2026-06-29",
            max_days=1,
            run_id=unittest.mock.ANY,
        )
        finish_run.assert_called_once()


if __name__ == "__main__":
    unittest.main()
