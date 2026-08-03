import unittest
from datetime import date
from io import BytesIO
from unittest.mock import patch

from openpyxl import load_workbook

from app.schedule_excel_import import (
    _afms_missing_from_sheet,
    _build_import_row,
    _format_time_cell,
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


class ScheduleExcelTimeCellTests(unittest.TestCase):
    def test_format_hhmm_digits(self):
        self.assertEqual(_format_time_cell(900), "09:00")
        self.assertEqual(_format_time_cell(1340), "13:40")
        self.assertEqual(_format_time_cell("0900"), "09:00")
        self.assertEqual(_format_time_cell("13:40"), "13:40")

    def test_format_excel_fraction_still_works(self):
        # 0.375 ημέρας = 09:00
        self.assertEqual(_format_time_cell(0.375), "09:00")

    def test_format_invalid_minutes(self):
        self.assertEqual(_format_time_cell(1399), "")
        self.assertEqual(_format_time_cell(2500), "")


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
        # Πάνω γραμμή εργαζομένου 1 · Από Δευτέρας (col 5).
        self.assertEqual(ws.cell(row=5, column=5).number_format, r"00\:00")
        self.assertEqual(ws.cell(row=5, column=4).value, None)  # Ενέργεια κενή by default
        # 2 γραμμές ανά εργαζόμενο: AFM μόνο στην πάνω (merged).
        self.assertEqual(str(ws.cell(row=5, column=1).value), "111111111")
        self.assertIsNone(ws.cell(row=6, column=1).value)

        # Δευτέρα ΡΕΠΟ · Τρίτη 09:00–17:00 · Τετάρτη σπαστό 10–14 + 17–21
        ws.cell(row=5, column=4, value="ΡΕΠΟ")
        ws.cell(row=5, column=8, value=900)   # Τρίτη Από
        ws.cell(row=5, column=9, value=1700)  # Τρίτη Έως
        ws.cell(row=5, column=11, value=1000)  # Τετάρτη Από1
        ws.cell(row=5, column=12, value=1400)  # Τετάρτη Έως1
        ws.cell(row=6, column=11, value=1700)  # Τετάρτη Από2 (κάτω γραμμή)
        ws.cell(row=6, column=12, value=2100)  # Τετάρτη Έως2
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

    def test_template_is_blank_hours(self):
        from app.schedule_excel_layout import employee_block_start_row, single_sheet_day_col

        week_monday = date(2026, 7, 6)
        store = {
            "id": 1,
            "name": "Test Store",
            "employer_afm": "123456789",
            "branch_aa": "0",
        }
        employees = [
            {"afm": "111111111", "eponymo": "TEST", "onoma": "ONE"},
        ]

        with patch("app.schedule_excel_template.get_store_config", return_value=store), patch(
            "app.schedule_excel_template.list_employees_for_employer", return_value=employees
        ):
            xlsx, _filename, meta = build_weekly_schedule_template_bytes(
                store_id=1,
                week_monday=week_monday,
            )

        self.assertEqual(meta.get("filled_day_slots"), "0")
        ws = load_workbook(filename=BytesIO(xlsx))[WEEK_SHEET]
        r1 = employee_block_start_row(0)
        r2 = r1 + 1
        self.assertEqual(ws.cell(row=r1, column=1).value, "111111111")
        for day_idx in range(7):
            self.assertIsNone(ws.cell(row=r1, column=single_sheet_day_col(day_idx, 0)).value)
            self.assertIsNone(ws.cell(row=r1, column=single_sheet_day_col(day_idx, 1)).value)
            self.assertIsNone(ws.cell(row=r1, column=single_sheet_day_col(day_idx, 2)).value)
            self.assertIsNone(ws.cell(row=r2, column=single_sheet_day_col(day_idx, 1)).value)
            self.assertIsNone(ws.cell(row=r2, column=single_sheet_day_col(day_idx, 2)).value)


if __name__ == "__main__":
    unittest.main()
