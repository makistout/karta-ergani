import unittest
from datetime import datetime, timedelta

from app.work_card_payload import (
    RETRO_AITIOLOGIA_INTERNET,
    WorkCardPayloadError,
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

    def test_check_in_on_time_no_aitiologia(self):
        ait = resolve_wrk_card_aitiologia(
            f_type="0",
            reference_date=self.today,
            event_at=f"{self.today}T10:00:00",
            requested_aitiologia="001",
            schedule_hour_from="10:00",
            flex_arrival_minutes=15,
        )
        self.assertIsNone(ait)

    def test_check_in_within_flex_no_aitiologia(self):
        ait = resolve_wrk_card_aitiologia(
            f_type="0",
            reference_date=self.today,
            event_at=f"{self.today}T10:15:00",
            requested_aitiologia=None,
            schedule_hour_from="10:00",
            flex_arrival_minutes=15,
        )
        self.assertIsNone(ait)

    def test_check_in_late_requires_aitiologia(self):
        ait = resolve_wrk_card_aitiologia(
            f_type="0",
            reference_date=self.today,
            event_at=f"{self.today}T10:20:00",
            requested_aitiologia=None,
            schedule_hour_from="10:00",
            flex_arrival_minutes=15,
        )
        self.assertEqual(ait, RETRO_AITIOLOGIA_INTERNET)

    def test_check_in_early_requires_aitiologia(self):
        ait = resolve_wrk_card_aitiologia(
            f_type="0",
            reference_date=self.today,
            event_at=f"{self.today}T09:45:00",
            requested_aitiologia=None,
            schedule_hour_from="10:00",
            flex_arrival_minutes=15,
        )
        self.assertEqual(ait, RETRO_AITIOLOGIA_INTERNET)

    def test_check_out_on_time_no_aitiologia(self):
        ait = resolve_wrk_card_aitiologia(
            f_type="1",
            reference_date=self.today,
            event_at=f"{self.today}T18:00:00",
            requested_aitiologia="001",
            schedule_hour_from="10:00",
            schedule_hour_to="18:00",
            flex_arrival_minutes=15,
        )
        self.assertIsNone(ait)

    def test_check_out_early_requires_aitiologia(self):
        ait = resolve_wrk_card_aitiologia(
            f_type="1",
            reference_date=self.today,
            event_at=f"{self.today}T17:40:00",
            requested_aitiologia=None,
            schedule_hour_from="10:00",
            schedule_hour_to="18:00",
            flex_arrival_minutes=15,
        )
        self.assertEqual(ait, RETRO_AITIOLOGIA_INTERNET)

    def test_previous_day_always_aitiologia(self):
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

    def test_payload_omits_f_aitiologia_when_none(self):
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
        self.assertNotIn("f_aitiologia", detail)

    def test_payload_can_include_null_f_aitiologia(self):
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
        self.assertIsNone(detail["f_aitiologia"])

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
