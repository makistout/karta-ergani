import unittest
from datetime import date
from unittest.mock import patch

from app.schedule_excel_import import (
    _afms_missing_from_sheet,
    _build_import_row,
    summarize_import_rows,
)
from app.schedule_excel_template import resolve_week_monday


class ScheduleExcelTemplateTests(unittest.TestCase):
    def test_resolve_week_monday_current_and_next(self):
        ref = date(2026, 7, 7)  # Tuesday
        self.assertEqual(resolve_week_monday("current", today=ref), date(2026, 7, 6))
        self.assertEqual(resolve_week_monday("next", today=ref), date(2026, 7, 13))


class ScheduleExcelImportAbsentTests(unittest.TestCase):
    def test_afms_missing_from_sheet_includes_known_and_scheduled(self):
        missing = _afms_missing_from_sheet(
            sheet_afms={"111111111"},
            known_afms={"111111111", "222222222"},
            current_schedule=[
                {"employee_afm": "333333333", "hour_from": "09:00", "hour_to": "17:00"},
            ],
        )
        self.assertEqual(missing, {"222222222", "333333333"})

    def test_absent_row_marks_working_employee_for_rest_update(self):
        current = [
            {
                "employee_afm": "162094518",
                "eponymo": "ΜΠΟΓΡΗΣ",
                "onoma": "ΓΕΩΡΓΙΟΣ",
                "hour_from": "11:00",
                "hour_to": "19:00",
                "shift_type": "ΕΡΓΑΣΙΑ",
            }
        ]
        row = _build_import_row(
            row_no=1,
            sheet_name="Τετάρτη 08-07",
            work_date="08/07/2026",
            afm="162094518",
            eponymo="ΜΠΟΓΡΗΣ",
            onoma="ΓΕΩΡΓΙΟΣ",
            import_action="absent",
            intervals=[],
            schedule_type="ΑΝ",
            current_schedule=current,
        )
        self.assertEqual(row["import_action"], "absent")
        self.assertEqual(row["change_kind"], "update")
        self.assertEqual(row["proposed_label"] if "proposed_label" in row else None, None)

    def test_absent_row_skips_when_already_rest(self):
        current = [
            {
                "employee_afm": "157216372",
                "eponymo": "ΠΡΩΤΟΥΛΗΣ",
                "shift_type": "ΑΝΑΠΑΥΣΗ/ΡΕΠΟ",
            }
        ]
        row = _build_import_row(
            row_no=1,
            sheet_name="Τετάρτη 08-07",
            work_date="08/07/2026",
            afm="157216372",
            eponymo="ΠΡΩΤΟΥΛΗΣ",
            onoma="ΒΑΣΙΛΕΙΟΣ",
            import_action="absent",
            intervals=[],
            schedule_type="ΑΝ",
            current_schedule=current,
        )
        self.assertEqual(row["change_kind"], "same")

    def test_summarize_counts_absent_rows(self):
        rows = [
            {"change_kind": "update", "import_action": "absent", "validation_errors": []},
            {"change_kind": "skip", "import_action": "skip", "validation_errors": []},
        ]
        summary = summarize_import_rows(rows)
        self.assertEqual(summary["absent"], 1)
        self.assertEqual(summary["apply"], 1)


if __name__ == "__main__":
    unittest.main()
