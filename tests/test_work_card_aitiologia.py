import unittest

from app.work_card_payload import build_wrk_card_se_payload, resolve_wrk_card_aitiologia


class WorkCardAitiologiaTests(unittest.TestCase):
    def test_check_in_at_schedule_start_omits_aitiologia(self):
        ait = resolve_wrk_card_aitiologia(
            f_type="0",
            event_at="2026-06-26T10:00:00",
            requested_aitiologia="001",
            schedule_hour_from="10:00",
            flex_arrival_minutes=15,
        )
        self.assertIsNone(ait)

    def test_check_in_late_requires_aitiologia(self):
        ait = resolve_wrk_card_aitiologia(
            f_type="0",
            event_at="2026-06-26T10:20:00",
            requested_aitiologia="001",
            schedule_hour_from="10:00",
            flex_arrival_minutes=15,
        )
        self.assertEqual(ait, "001")

    def test_check_out_keeps_aitiologia(self):
        ait = resolve_wrk_card_aitiologia(
            f_type="1",
            event_at="2026-06-26T18:00:00",
            requested_aitiologia="001",
            schedule_hour_from="10:00",
            schedule_hour_to="18:00",
        )
        self.assertEqual(ait, "001")

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


if __name__ == "__main__":
    unittest.main()
