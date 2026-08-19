from io import BytesIO
from datetime import timedelta

from openpyxl import load_workbook

from app.timekeeping_export import build_timekeeping_export_xlsx


def test_timekeeping_export_has_summary_and_daily_sheets_with_typed_durations():
    report = {
        "employees": [{
            "employee_afm": "012345678", "eponymo": "ΔΟΚΙΜΗ", "onoma": "ΕΝΑ",
            "recognized_work_minutes": 480, "day": 420, "night": 60,
            "sunday_holiday": 0, "night_sunday_holiday": 0,
            "partial_additional_12": 0, "sixth_day_minutes": 0,
            "overtime_40": 30, "overtime_60": 0, "overtime_120": 0,
            "partial_120": 0, "annual_legal_overtime_minutes_after_period": 300,
        }],
        "days": [{
            "work_date": "03/08/2026", "employee_afm": "012345678",
            "eponymo": "ΔΟΚΙΜΗ", "onoma": "ΕΝΑ", "status": "ok",
            "basis_source": "declared_compliant", "basis_label": "14:00–22:00",
            "break_interval": "", "recognized_work_minutes": 480,
            "premium_minutes": {"day": 420, "night": 60, "sunday_holiday": 0, "night_sunday_holiday": 0},
            "partial_additional_12": 0, "sixth_day_minutes": 0,
            "overtime_40": 30, "overtime_60": 0, "overtime_120": 0, "partial_120": 0,
            "warnings": [],
        }],
    }
    content = build_timekeeping_export_xlsx(report=report, meta_line="Store · 03/08/2026–09/08/2026")
    workbook = load_workbook(BytesIO(content), data_only=False)
    assert workbook.sheetnames == ["Σύνοψη", "Ανά ημέρα"]
    assert workbook["Σύνοψη"]["B4"].value == "012345678"
    assert workbook["Σύνοψη"]["C4"].value == timedelta(hours=8)
    assert workbook["Σύνοψη"]["C4"].number_format == "[h]:mm"
    assert workbook["Ανά ημέρα"]["F4"].value == "14:00–22:00"
