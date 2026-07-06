import unittest
from datetime import datetime

from app.work_card_payload import (
    RETRO_AITIOLOGIA_INTERNET,
    build_wrk_card_se_payload,
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


if __name__ == "__main__":
    unittest.main()
