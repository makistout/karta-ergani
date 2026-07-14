import unittest
from datetime import date
from io import BytesIO
from unittest.mock import patch

from openpyxl import load_workbook

from app.schedule_excel_import import (
    _afms_missing_from_sheet,
    _build_import_row,
    parse_weekly_schedule_workbook,
    summarize_import_rows,
)
from app.schedule_excel_layout import WEEK_SHEET
from app.schedule_excel_template import build_weekly_schedule_template_bytes, resolve_week_monday


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


class ScheduleExcelSingleSheetTests(unittest.TestCase):
    def test_single_sheet_template_and_parse_roundtrip(self):
        week_monday = date(2026, 7, 6)
        store = {
            "id": 1,
            "name": "Test Store",
            "employer_afm": "123456789",
            "branch_aa": "0",
        }
        employees = [
            {"afm": "111111111", "eponymo": "TEST", "onoma": "ONE"},
            {"afm": "222222222", "eponymo": "TEST", "onoma": "TWO"},
        ]

        with patch("app.schedule_excel_template.get_store_config", return_value=store), patch(
            "app.schedule_excel_template.list_employees_for_employer", return_value=employees
        ):
            xlsx, _filename, _meta = build_weekly_schedule_template_bytes(
                store_id=1,
                week_monday=week_monday,
            )

        wb = load_workbook(filename=BytesIO(xlsx))
        self.assertIn(WEEK_SHEET, wb.sheetnames)
        self.assertEqual(len(wb.sheetnames), 2)

        ws = wb[WEEK_SHEET]
        ws.cell(row=5, column=4, value="ΡΕΠΟ")
        ws.cell(row=5, column=10, value="09:00")
        ws.cell(row=5, column=11, value="17:00")
        ws.cell(row=5, column=15, value="10:00")
        ws.cell(row=5, column=16, value="14:00")
        ws.cell(row=5, column=17, value="17:00")
        ws.cell(row=5, column=18, value="21:00")
        bio = BytesIO()
        wb.save(bio)
        filled = bio.getvalue()

        with patch(
            "app.schedule_excel_import.list_employees_for_employer", return_value=employees
        ), patch("app.schedule_excel_import.list_schedule_for_store", return_value=[]):
            parsed = parse_weekly_schedule_workbook(
                filled,
                employer_afm="123456789",
                branch_aa="0",
            )

        self.assertEqual(parsed["work_dates"], [
            "06/07/2026",
            "07/07/2026",
            "08/07/2026",
            "09/07/2026",
            "10/07/2026",
            "11/07/2026",
            "12/07/2026",
        ])
        rows = parsed["rows"]
        self.assertEqual(len(rows), 14)
        mon_repo = [r for r in rows if r["employee_afm"] == "111111111" and r["work_date"] == "06/07/2026"][0]
        self.assertEqual(mon_repo["import_action"], "rest")
        tue_work = [r for r in rows if r["employee_afm"] == "111111111" and r["work_date"] == "07/07/2026"][0]
        self.assertEqual(tue_work["import_action"], "work")
        self.assertEqual(tue_work["hour_from_1"], "09:00")
        self.assertEqual(tue_work["hour_to_1"], "17:00")
        wed_split = [r for r in rows if r["employee_afm"] == "111111111" and r["work_date"] == "08/07/2026"][0]
        self.assertEqual(wed_split["hour_from_2"], "17:00")
        self.assertEqual(wed_split["hour_to_2"], "21:00")
        skips = [r for r in rows if r["import_action"] == "skip"]
        self.assertGreater(len(skips), 0)


if __name__ == "__main__":
    unittest.main()
