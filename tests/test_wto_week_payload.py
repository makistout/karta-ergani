from __future__ import annotations

import unittest

from app.work_card_payload import WorkCardPayloadError
from app.wto_week_payload import build_wto_week_payload


def standard_days():
    return [
        {
            "day": day,
            "entries": [{"type": "ΕΡΓ", "from": "09:00", "to": "17:00"}],
        }
        for day in (1, 2, 3, 4, 5)
    ] + [
        {"day": 6, "entries": [{"type": "ΑΝ"}]},
        {"day": 0, "entries": [{"type": "ΑΝ"}]},
    ]


class WtoWeekPayloadTests(unittest.TestCase):
    def test_builds_all_seven_employee_day_rows(self):
        payload = build_wto_week_payload(
            branch_aa="0",
            employee_afm="123456789",
            employee_last_name="ΠΑΠΑΔΟΠΟΥΛΟΣ",
            employee_first_name="ΝΙΚΟΣ",
            from_date="2026-06-29",
            days=standard_days(),
        )
        wto = payload["WTOS"]["WTO"][0]
        self.assertEqual(wto["f_from_date"], "29/06/2026")
        self.assertEqual(wto["f_to_date"], " ")
        rows = wto["Ergazomenoi"]["ErgazomenoiWTO"]
        self.assertEqual([row["f_day"] for row in rows], ["1", "2", "3", "4", "5", "6", "0"])
        self.assertEqual(
            rows[0]["ErgazomenosAnalytics"]["ErgazomenosWTOAnalytics"][0],
            {"f_type": "ΕΡΓ", "f_from": "09:00", "f_to": "17:00"},
        )
        self.assertEqual(
            rows[-1]["ErgazomenosAnalytics"]["ErgazomenosWTOAnalytics"][0],
            {"f_type": "ΑΝ", "f_from": " ", "f_to": " "},
        )

    def test_supports_split_shift(self):
        days = standard_days()
        days[0]["entries"] = [
            {"type": "ΕΡΓ", "from": "09:00", "to": "13:00"},
            {"type": "ΕΡΓ", "from": "17:00", "to": "21:00"},
        ]
        payload = build_wto_week_payload(
            branch_aa="1",
            employee_afm="123456789",
            employee_last_name="ΠΑΠΑΔΟΠΟΥΛΟΣ",
            employee_first_name="ΝΙΚΟΣ",
            from_date="2026-06-29",
            to_date="2026-12-31",
            days=days,
        )
        analytics = payload["WTOS"]["WTO"][0]["Ergazomenoi"]["ErgazomenoiWTO"][0][
            "ErgazomenosAnalytics"
        ]["ErgazomenosWTOAnalytics"]
        self.assertEqual(len(analytics), 2)
        self.assertEqual(payload["WTOS"]["WTO"][0]["f_to_date"], "31/12/2026")

    def test_rejects_missing_day(self):
        with self.assertRaisesRegex(WorkCardPayloadError, "ημέρες 0–6"):
            build_wto_week_payload(
                branch_aa="0",
                employee_afm="123456789",
                employee_last_name="ΠΑΠΑΔΟΠΟΥΛΟΣ",
                employee_first_name="ΝΙΚΟΣ",
                from_date="2026-06-29",
                days=standard_days()[:-1],
            )

    def test_rejects_rest_mixed_with_work(self):
        days = standard_days()
        days[0]["entries"] = [
            {"type": "ΑΝ"},
            {"type": "ΕΡΓ", "from": "09:00", "to": "17:00"},
        ]
        with self.assertRaisesRegex(WorkCardPayloadError, "δεν συνδυάζεται"):
            build_wto_week_payload(
                branch_aa="0",
                employee_afm="123456789",
                employee_last_name="ΠΑΠΑΔΟΠΟΥΛΟΣ",
                employee_first_name="ΝΙΚΟΣ",
                from_date="2026-06-29",
                days=days,
            )

    def test_rejects_invalid_time(self):
        days = standard_days()
        days[0]["entries"][0]["from"] = "25:00"
        with self.assertRaisesRegex(WorkCardPayloadError, "ΩΩ:ΛΛ"):
            build_wto_week_payload(
                branch_aa="0",
                employee_afm="123456789",
                employee_last_name="ΠΑΠΑΔΟΠΟΥΛΟΣ",
                employee_first_name="ΝΙΚΟΣ",
                from_date="2026-06-29",
                days=days,
            )


if __name__ == "__main__":
    unittest.main()
