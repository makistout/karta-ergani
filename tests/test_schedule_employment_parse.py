"""Tests για parse απασχόλησης portal και rest-day detection."""

from __future__ import annotations

import unittest

from app.card_report import _expand_schedule_hours_from_shift_type, _is_rest_day
from app.ergani_parse import parse_employment_cell, portal_rows_to_schedule_items


class ParseEmploymentCellTests(unittest.TestCase):
    def test_single_interval(self):
        self.assertEqual(
            parse_employment_cell("ΕΡΓΑΣΙΑ 09:00-17:00"),
            [("ΕΡΓΑΣΙΑ", "09:00", "17:00")],
        )

    def test_split_intervals(self):
        self.assertEqual(
            parse_employment_cell("ΕΡΓΑΣΙΑ 11:00-16:00 ΕΡΓΑΣΙΑ 20:30-23:30"),
            [
                ("ΕΡΓΑΣΙΑ", "11:00", "16:00"),
                ("ΕΡΓΑΣΙΑ", "20:30", "23:30"),
            ],
        )

    def test_rest_text_has_no_intervals(self):
        self.assertEqual(parse_employment_cell("ΑΝΑΠΑΥΣΗ/ΡΕΠΟ"), [])


class PortalRowsToScheduleItemsTests(unittest.TestCase):
    def test_split_emits_two_rows(self):
        grid = [[
            "0",
            "301110964",
            "GALYA",
            "BONEVA",
            "22/07/2026",
            "",
            "",
            "Εντός",
            "ΕΡΓΑΣΙΑ 11:00-16:00 ΕΡΓΑΣΙΑ 20:30-23:30",
        ]]
        items = portal_rows_to_schedule_items(grid, default_work_date="22/07/2026")
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0]["hour_from"], "11:00")
        self.assertEqual(items[0]["hour_to"], "16:00")
        self.assertEqual(items[1]["hour_from"], "20:30")
        self.assertEqual(items[1]["hour_to"], "23:30")
        self.assertEqual(items[0]["shift_type"], "ΕΡΓΑΣΙΑ")


class RestDayDetectionTests(unittest.TestCase):
    def test_explicit_rest(self):
        self.assertTrue(_is_rest_day("ΑΝΑΠΑΥΣΗ/ΡΕΠΟ", "", ""))

    def test_work_hours_not_rest(self):
        self.assertFalse(_is_rest_day("ΕΡΓΑΣΙΑ", "11:00", "16:00"))

    def test_blob_shift_without_hours_not_auto_rest(self):
        # Παλιό bug: οποιοδήποτε shift_type χωρίς ώρες → ρεπό.
        self.assertFalse(
            _is_rest_day("ΕΡΓΑΣΙΑ 11:00-16:00 ΕΡΓΑΣΙΑ 20:30-23:30", "", "")
        )

    def test_expand_blob_into_intervals(self):
        expanded = _expand_schedule_hours_from_shift_type(
            {
                "hour_from": "",
                "hour_to": "",
                "shift_type": "ΕΡΓΑΣΙΑ 11:00-16:00 ΕΡΓΑΣΙΑ 20:30-23:30",
                "intervals": [],
            }
        )
        assert expanded is not None
        self.assertEqual(expanded["hour_from"], "11:00")
        self.assertEqual(expanded["hour_to"], "23:30")
        self.assertEqual(len(expanded["intervals"]), 2)
        self.assertEqual(expanded["shift_type"], "ΕΡΓΑΣΙΑ")
        self.assertFalse(
            _is_rest_day(
                expanded["shift_type"],
                expanded["hour_from"],
                expanded["hour_to"],
            )
        )


if __name__ == "__main__":
    unittest.main()
