import unittest
from datetime import datetime, timedelta

from app.work_card_payload import (
    RETRO_AITIOLOGIA_INTERNET,
    WorkCardPayloadError,
    aitiologia_for_wrk_card_submit,
    build_wrk_card_se_payload,
    event_at_is_future,
    ergani_forbids_aitiologia,
    resolve_wrk_card_aitiologia,
    tz_athens,
    wrk_card_needs_aitiologia,
)


class WorkCardAitiologiaTests(unittest.TestCase):
    def setUp(self):
        self.today = datetime.now(tz_athens()).date().isoformat()

    def test_check_in_submitted_within_limit_no_aitiologia(self):
        event = datetime.now(tz_athens()).replace(second=0, microsecond=0)
        ait = resolve_wrk_card_aitiologia(
            f_type="0",
            reference_date=event.date().isoformat(),
            event_at=event.isoformat(),
            requested_aitiologia="001",
            schedule_hour_from="10:00",
            flex_arrival_minutes=15,
            submitted_at=event + timedelta(minutes=10),
        )
        self.assertIsNone(ait)

    def test_submission_within_fifteen_minutes_has_no_aitiologia(self):
        submitted = datetime.now(tz_athens()).replace(second=0, microsecond=0)
        ait = resolve_wrk_card_aitiologia(
            f_type="0",
            reference_date=submitted.date().isoformat(),
            event_at=(submitted - timedelta(minutes=15)).isoformat(),
            requested_aitiologia=None,
            schedule_hour_from="01:00",
            flex_arrival_minutes=0,
            submitted_at=submitted,
        )
        self.assertIsNone(ait)

    def test_submission_after_fifteen_minutes_requires_aitiologia(self):
        submitted = datetime.now(tz_athens()).replace(second=0, microsecond=0)
        ait = resolve_wrk_card_aitiologia(
            f_type="0",
            reference_date=submitted.date().isoformat(),
            event_at=(submitted - timedelta(minutes=15, seconds=1)).isoformat(),
            requested_aitiologia=None,
            schedule_hour_from="23:00",
            flex_arrival_minutes=120,
            submitted_at=submitted,
        )
        self.assertEqual(ait, RETRO_AITIOLOGIA_INTERNET)

    def test_ten_minutes_ago_never_sends_aitiologia_regardless_of_schedule(self):
        submitted = datetime(2026, 8, 26, 19, 28, tzinfo=tz_athens())
        ait = resolve_wrk_card_aitiologia(
            f_type="0",
            reference_date="2026-08-26",
            event_at="2026-08-26T19:18:00+03:00",
            requested_aitiologia="001",
            schedule_hour_from="09:00",
            flex_arrival_minutes=0,
            submitted_at=submitted,
        )
        self.assertIsNone(ait)

    def test_schedule_difference_does_not_add_aitiologia_within_limit(self):
        event = datetime.now(tz_athens()).replace(second=0, microsecond=0)
        ait = resolve_wrk_card_aitiologia(
            f_type="0",
            reference_date=event.date().isoformat(),
            event_at=event.isoformat(),
            requested_aitiologia=None,
            schedule_hour_from="23:00",
            flex_arrival_minutes=0,
            submitted_at=event + timedelta(minutes=10),
        )
        self.assertIsNone(ait)

    def test_check_in_submitted_after_limit_requires_aitiologia(self):
        event = datetime.now(tz_athens()).replace(second=0, microsecond=0)
        ait = resolve_wrk_card_aitiologia(
            f_type="0",
            reference_date=event.date().isoformat(),
            event_at=event.isoformat(),
            requested_aitiologia=None,
            schedule_hour_from="10:00",
            flex_arrival_minutes=120,
            submitted_at=event + timedelta(minutes=16),
        )
        self.assertEqual(ait, RETRO_AITIOLOGIA_INTERNET)

    def test_flex_does_not_control_aitiologia(self):
        event = datetime.now(tz_athens()).replace(second=0, microsecond=0)
        ait = resolve_wrk_card_aitiologia(
            f_type="0",
            reference_date=event.date().isoformat(),
            event_at=event.isoformat(),
            requested_aitiologia="001",
            schedule_hour_from="09:00",
            flex_arrival_minutes=15,
            submitted_at=event + timedelta(minutes=5),
        )
        self.assertIsNone(ait)

    def test_immediate_punch_no_aitiologia_even_if_late_vs_schedule(self):
        now = datetime.now(tz_athens()).replace(second=0, microsecond=0)
        ait = resolve_wrk_card_aitiologia(
            f_type="0",
            reference_date=now.date().isoformat(),
            event_at=now.isoformat(timespec="seconds"),
            requested_aitiologia=None,
            schedule_hour_from="09:00",
            flex_arrival_minutes=15,
            submitted_at=now,
        )
        self.assertIsNone(ait)

    def test_retro_with_now_time_same_as_immediate_punch(self):
        """Retro σήμερα+τώρα = ίδια λογική με live (όχι από κανάλι)."""
        now = datetime.now(tz_athens()).replace(second=0, microsecond=0)
        ait = resolve_wrk_card_aitiologia(
            f_type="0",
            reference_date=now.date().isoformat(),
            event_at=now.isoformat(timespec="seconds"),
            requested_aitiologia="001",
            schedule_hour_from="09:00",
            flex_arrival_minutes=15,
            submitted_at=now,
        )
        self.assertIsNone(ait)

    def test_check_out_submitted_within_limit_no_aitiologia(self):
        event = datetime.now(tz_athens()).replace(second=0, microsecond=0)
        ait = resolve_wrk_card_aitiologia(
            f_type="1",
            reference_date=event.date().isoformat(),
            event_at=event.isoformat(),
            requested_aitiologia="001",
            schedule_hour_from="10:00",
            schedule_hour_to="18:00",
            flex_arrival_minutes=15,
            submitted_at=event + timedelta(minutes=10),
        )
        self.assertIsNone(ait)

    def test_check_out_submitted_after_limit_requires_aitiologia(self):
        event = datetime.now(tz_athens()).replace(second=0, microsecond=0)
        ait = resolve_wrk_card_aitiologia(
            f_type="1",
            reference_date=event.date().isoformat(),
            event_at=event.isoformat(),
            requested_aitiologia=None,
            schedule_hour_from="10:00",
            schedule_hour_to="18:00",
            flex_arrival_minutes=15,
            submitted_at=event + timedelta(minutes=16),
        )
        self.assertEqual(ait, RETRO_AITIOLOGIA_INTERNET)

    def test_previous_day_requires_aitiologia_when_more_than_fifteen_minutes_old(self):
        self.assertTrue(
            wrk_card_needs_aitiologia(
                f_type="0",
                reference_date="2020-01-01",
                event_at="2020-01-01T10:00:00",
                schedule_hour_from="10:00",
                flex_arrival_minutes=15,
            )
        )
        ait = resolve_wrk_card_aitiologia(
            f_type="0",
            reference_date="2020-01-01",
            event_at="2020-01-01T10:00:00",
            requested_aitiologia=None,
            schedule_hour_from="10:00",
            flex_arrival_minutes=15,
        )
        self.assertEqual(ait, RETRO_AITIOLOGIA_INTERNET)

    def test_payload_uses_empty_f_aitiologia_when_none(self):
        payload = build_wrk_card_se_payload(
            employer_afm="123456789",
            branch_aa="0",
            employee_afm="987654321",
            employee_last_name="Test",
            employee_first_name="User",
            event="check_in",
            reference_date="2026-06-26",
            event_at="2026-06-26T10:00:00",
            aitiologia=None,
        )
        detail = payload["Cards"]["Card"][0]["Details"]["CardDetails"][0]
        self.assertEqual(detail["f_aitiologia"], "")

    def test_payload_can_include_null_f_aitiologia_legacy_flag(self):
        payload = build_wrk_card_se_payload(
            employer_afm="123456789",
            branch_aa="0",
            employee_afm="987654321",
            employee_last_name="Test",
            employee_first_name="User",
            event="check_in",
            reference_date="2026-06-26",
            event_at="2026-06-26T10:00:00",
            aitiologia=None,
            include_null_aitiologia=True,
        )
        detail = payload["Cards"]["Card"][0]["Details"]["CardDetails"][0]
        self.assertEqual(detail["f_aitiologia"], "")

    def test_payload_rejects_future_event_for_every_submission_channel(self):
        future = datetime.now(tz_athens()) + timedelta(minutes=10)
        with self.assertRaisesRegex(WorkCardPayloadError, "μελλοντική"):
            build_wrk_card_se_payload(
                employer_afm="123456789",
                branch_aa="0",
                employee_afm="987654321",
                employee_last_name="Test",
                employee_first_name="User",
                event="check_out",
                reference_date=future.date().isoformat(),
                event_at=future.isoformat(),
            )

    def test_payload_rejects_future_reference_date_without_event_at(self):
        tomorrow = (datetime.now(tz_athens()) + timedelta(days=1)).date().isoformat()
        with self.assertRaisesRegex(WorkCardPayloadError, "μελλοντική"):
            build_wrk_card_se_payload(
                employer_afm="123456789",
                branch_aa="0",
                employee_afm="987654321",
                employee_last_name="Test",
                employee_first_name="User",
                event="check_in",
                reference_date=tomorrow,
            )

    def test_future_guard_accepts_current_or_past_event(self):
        now = datetime(2026, 8, 11, 1, 36, 10, tzinfo=tz_athens())
        self.assertTrue(event_at_is_future(
            datetime(2026, 8, 11, 1, 49, tzinfo=tz_athens()), now=now
        ))
        self.assertFalse(event_at_is_future(
            datetime(2026, 8, 11, 1, 36, tzinfo=tz_athens()), now=now
        ))

    def test_routes_detects_ergani_xsd_aitiologia_requirement(self):
        from app.routes_work_card import _ergani_missing_aitiologia

        self.assertTrue(_ergani_missing_aitiologia({
            "message": (
                "The element 'CardDetails' has incomplete content. "
                "List of possible elements expected: 'f_aitiologia'."
            )
        }))
        self.assertFalse(_ergani_missing_aitiologia({
            "message": "Δεν πρέπει να δηλώνεται λόγος καθυστέρησης"
        }))
        self.assertTrue(_ergani_missing_aitiologia({
            "message": "Πρέπει να συμπληρώσετε τον λόγο καθυστέρησης"
        }))

    def test_ergani_forbids_aitiologia_detects_auto_close_style_error(self):
        msg = (
            "Ergani (400): Για το Παράρτημα: 0\n"
            "Για την κίνηση αποχώρησης με ΑΦΜ '122643591' στις 05/08/2026 βρέθηκαν τα παρακάτω λάθη: \n"
            "Η δηλωμένη ώρα κίνησης είναι μεγαλύτερη και αποκλίνει σημαντικά της τωρινής ώρας (01:57).\n"
            "Δεν πρέπει να δηλώνεται λόγος καθυστέρησης, όταν η ώρα κίνησης είναι εντός του επιτρεπόμενου χρονικού ορίου.\n"
        )
        self.assertTrue(ergani_forbids_aitiologia({"error": msg}))
        self.assertFalse(ergani_forbids_aitiologia({"error": "άλλη αποτυχία"}))


if __name__ == "__main__":
    unittest.main()
