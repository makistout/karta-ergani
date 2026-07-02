import unittest
from datetime import datetime
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

    def test_scheduled_sync_fetches_today_only(self):
        class FakeLogger:
            def __init__(self, *args, **kwargs):
                self.run_id = "run-test"

            def info(self, *args, **kwargs):
                return None

            def warning(self, *args, **kwargs):
                return None

            def error(self, *args, **kwargs):
                return None

        cfg = {
            "id": 7,
            "name": "Demo",
            "employer_afm": "123456789",
            "branch_aa": "0",
            "username": "portal-user",
            "password": "portal-pass",
        }
        schedule_result = {
            "success": True,
            "count": 3,
            "days_synced": 3,
            "fetch_source": "excel",
        }
        work_log_result = {"success": True, "count": 1, "fetch_source": "excel"}

        with (
            patch("app.scheduled_sync.KartaLogger", FakeLogger),
            patch(
                "app.scheduled_sync.sync_schedule_from_portal",
                return_value=schedule_result,
            ) as schedule_sync,
            patch(
                "app.scheduled_sync.sync_work_log_from_portal",
                return_value=work_log_result,
            ) as work_log_sync,
            patch("app.scheduled_sync.repo_sync_log.finish_run"),
            patch("app.scheduled_sync.repo_store.get_store_config", return_value=cfg),
            patch(
                "app.scheduled_sync.enqueue_post_sync_notifications",
                return_value=False,
            ),
            patch("app.scheduled_sync._run_configured_auto_actions", return_value=None),
        ):
            result = scheduled_sync.sync_store_today(
                cfg,
                work_date_iso="2026-07-02",
            )

        self.assertTrue(result["success"])
        schedule_kwargs = schedule_sync.call_args.kwargs
        self.assertEqual(schedule_kwargs["from_iso"], "2026-07-02")
        self.assertEqual(schedule_kwargs["to_iso"], "2026-07-02")
        self.assertEqual(schedule_kwargs["max_days"], 1)
        work_log_kwargs = work_log_sync.call_args.kwargs
        self.assertEqual(work_log_kwargs["from_iso"], "2026-07-02")
        self.assertEqual(work_log_kwargs["to_iso"], "2026-07-02")
        self.assertEqual(work_log_kwargs["max_days"], 1)

    def test_future_schedule_auto_action_runs_once_after_configured_time(self):
        cfg = {
            "id": 7,
            "name": "Demo",
            "auto_close_prev_day_time": "00:30",
        }
        with (
            patch("app.scheduled_sync.repo_sync_log.tables_available", return_value=True),
            patch(
                "app.scheduled_sync._future_schedule_sync_run_exists",
                return_value=False,
            ),
        ):
            should_run, from_iso, to_iso, reason = (
                scheduled_sync.should_run_future_schedule_sync(
                    cfg,
                    now=datetime(2026, 7, 2, 0, 31),
                )
            )

        self.assertTrue(should_run)
        self.assertEqual(from_iso, "2026-07-03")
        self.assertEqual(to_iso, "2026-07-04")
        self.assertEqual(reason, "έτοιμο")

    def test_configured_auto_actions_runs_future_schedule_separately(self):
        cfg = {
            "id": 7,
            "name": "Demo",
            "auto_close_prev_day_enabled": False,
        }
        future_result = {
            "success": True,
            "from_iso": "2026-07-03",
            "to_iso": "2026-07-04",
        }

        with (
            patch(
                "app.scheduled_sync.should_run_future_schedule_sync",
                return_value=(True, "2026-07-03", "2026-07-04", "έτοιμο"),
            ),
            patch(
                "app.scheduled_sync.run_future_schedule_sync_for_store",
                return_value=future_result,
            ) as future_sync,
            patch(
                "app.auto_close_cards.should_run_auto_close_prev_day",
                return_value=(False, "2026-07-01", "ρύθμιση ανενεργή"),
            ),
        ):
            actions = scheduled_sync._run_configured_auto_actions(
                cfg,
                parent_run_id="parent",
            )

        future_sync.assert_called_once_with(
            cfg,
            from_iso="2026-07-03",
            to_iso="2026-07-04",
        )
        self.assertEqual(actions["future_schedule"], future_result)
        self.assertTrue(actions["auto_close_prev_day"]["skipped"])

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
