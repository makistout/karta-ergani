import unittest
from unittest.mock import patch

from app.routes_wto_daily import _persist_local_schedule_after_wto_daily


class WtoDailyLocalScheduleTests(unittest.TestCase):
    def _payload(self):
        return {"WTOS": {"WTO": [{"f_from_date": "2026-07-02"}]}}

    def test_persist_local_schedule_after_wto_daily_updates_hours(self):
        ctx = {"employer_afm": " 123456789 ", "branch_aa": "2"}
        body = {
            "schedule_type": "ΕΡΓ",
            "hour_from": "10:00",
            "hour_to": "18:00",
        }

        with patch("app.routes_wto_daily.upsert_schedule_for_employee_day") as upsert:
            self.assertTrue(
                _persist_local_schedule_after_wto_daily(
                    ctx,
                    employee_afm=" 987654321 ",
                    body=body,
                    payload=self._payload(),
                )
            )

        upsert.assert_called_once_with(
            " 123456789 ",
            "2",
            "2026-07-02",
            employee_afm=" 987654321 ",
            hour_from="10:00",
            hour_to="18:00",
            shift_type="ΕΡΓ",
            extra="local WTODaily submit",
            source_aa="local_wto_daily",
        )

    def test_persist_local_schedule_after_wto_daily_updates_rest_day(self):
        ctx = {"employer_afm": "123456789", "branch_aa": "0"}
        body = {
            "schedule_type": "AN",
            "hour_from": "10:00",
            "hour_to": "18:00",
        }

        with patch("app.routes_wto_daily.upsert_schedule_for_employee_day") as upsert:
            self.assertTrue(
                _persist_local_schedule_after_wto_daily(
                    ctx,
                    employee_afm="987654321",
                    body=body,
                    payload=self._payload(),
                )
            )

        upsert.assert_called_once_with(
            "123456789",
            "0",
            "2026-07-02",
            employee_afm="987654321",
            hour_from=None,
            hour_to=None,
            shift_type="Ρεπό/ανάπαυση",
            extra="local WTODaily submit",
            source_aa="local_wto_daily",
        )


if __name__ == "__main__":
    unittest.main()
