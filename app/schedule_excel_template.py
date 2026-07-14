"""Δημιουργία κενού Excel template εβδομαδιαίου ωραρίου (ένα φύλλο)."""

from __future__ import annotations

import re
from datetime import date, timedelta
from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

from app.repo_entities import list_employees_for_employer
from app.repo_store import get_store_config
from app.schedule_excel_layout import (
    BASE_COL_COUNT,
    BASE_HEADERS,
    DAY_COUNT,
    DAY_FIELD_COUNT,
    DAY_FIELD_HEADERS,
    INSTRUCTIONS_SHEET,
    SINGLE_SHEET_DATA_START_ROW,
    SINGLE_SHEET_HEADER_ROW_DAY,
    SINGLE_SHEET_HEADER_ROW_FIELDS,
    WEEK_SHEET,
    single_sheet_day_col,
    single_sheet_last_col,
)

DAYS = [
    ("Δευτέρα", 0),
    ("Τρίτη", 1),
    ("Τετάρτη", 2),
    ("Πέμπτη", 3),
    ("Παρασκευή", 4),
    ("Σάββατο", 5),
    ("Κυριακή", 6),
]


def resolve_week_monday(which: str, *, today: date | None = None) -> date:
    ref = today or date.today()
    monday = ref - timedelta(days=ref.weekday())
    key = str(which or "").strip().lower()
    if key == "next":
        return monday + timedelta(days=7)
    if key == "current":
        return monday
    raise ValueError("Μη έγκυρη εβδομάδα — επιτρέπονται current ή next")


def _safe_filename_part(value: str, *, fallback: str = "store") -> str:
    text = re.sub(r"[^\w\-]+", "_", str(value or "").strip(), flags=re.UNICODE)
    text = re.sub(r"_+", "_", text).strip("_")
    return (text[:48] or fallback)


def build_weekly_schedule_template_bytes(
    *,
    store_id: int,
    week_monday: date,
) -> tuple[bytes, str, dict[str, str]]:
    store = get_store_config(int(store_id))
    if not store:
        raise ValueError(f"Δεν βρέθηκε κατάστημα id={store_id}")

    employees = list_employees_for_employer(store["employer_afm"], store["branch_aa"])
    sunday = week_monday + timedelta(days=6)
    last_col = single_sheet_last_col()
    last_letter = get_column_letter(last_col)

    thin = Side(style="thin", color="D9E2F2")
    border = Border(left=thin, right=thin, top=thin, bottom=thin)
    header_fill = PatternFill("solid", fgColor="1F4E78")
    day_fill = PatternFill("solid", fgColor="2E75B6")
    warn_fill = PatternFill("solid", fgColor="FFF2CC")
    header_font = Font(color="FFFFFF", bold=True)
    day_font = Font(color="FFFFFF", bold=True, size=10)
    center = Alignment(horizontal="center", vertical="center", wrap_text=True)

    wb = Workbook()
    info = wb.active
    info.title = INSTRUCTIONS_SHEET
    info["A1"] = f"Εβδομαδιαίο ωράριο - {store['name']}"
    info["A1"].font = Font(bold=True, size=14)
    info["A2"] = f"Εβδομάδα {week_monday.strftime('%d/%m/%Y')} - {sunday.strftime('%d/%m/%Y')}"
    info["A2"].font = Font(bold=True, size=11)
    instructions = [
        "",
        "Οδηγίες:",
        "1. Όλες οι ημέρες της εβδομάδας είναι στο φύλλο «Εβδομάδα».",
        "2. Μία γραμμή ανά εργαζόμενο· κάθε ημέρα έχει 5 στήλες.",
        "3. Ανά ημέρα: Ενέργεια, Από1, Έως1, Από2, Έως2.",
        "4. Στήλη Ενέργεια: μόνο ΡΕΠΟ ή κενό.",
        "   - ΡΕΠΟ = ρεπό εκείνη την ημέρα (οι ώρες αγνοούνται).",
        "   - Κενό + ώρες συμπληρωμένες = αλλαγή ωραρίου.",
        "   - Κενό + κενές ώρες = καμία αλλαγή για την ημέρα.",
        "5. Οι ώρες γράφονται ΩΩ:ΛΛ (π.χ. 09:00, 17:30).",
        "6. Για σπαστό ωράριο συμπλήρωσε και Από2/Έως2 (2ο διάστημα).",
    ]
    r = 3
    for text in instructions:
        info[f"A{r}"] = text
        r += 1
    info["A16"] = "Store ID"
    info["B16"] = int(store_id)
    info["A17"] = "Employer AFM"
    info["B17"] = store["employer_afm"]
    info["A18"] = "Branch AA"
    info["B18"] = store["branch_aa"]
    info.column_dimensions["A"].width = 44
    info.column_dimensions["B"].width = 24

    ws = wb.create_sheet(WEEK_SHEET)
    ws["A1"] = (
        f"Εβδομαδιαίο ωράριο — {week_monday.strftime('%d/%m/%Y')} έως "
        f"{sunday.strftime('%d/%m/%Y')}"
    )
    ws["A1"].font = Font(bold=True, size=12)
    ws.merge_cells(f"A1:{last_letter}1")
    ws["A2"] = (
        "Ενέργεια: ΡΕΠΟ ή κενό  |  Ώρες: ΩΩ:ΛΛ  |  "
        "Σπαστό: συμπλήρωσε Από2/Έως2"
    )
    ws["A2"].font = Font(italic=True)
    ws["A2"].fill = warn_fill
    ws.merge_cells(f"A2:{last_letter}2")

    for day_idx, (day_name, offset) in enumerate(DAYS):
        d = week_monday + timedelta(days=offset)
        start_col = single_sheet_day_col(day_idx, 0)
        end_col = single_sheet_day_col(day_idx, DAY_FIELD_COUNT - 1)
        cell = ws.cell(
            row=SINGLE_SHEET_HEADER_ROW_DAY,
            column=start_col,
            value=f"{day_name}\n{d.strftime('%d/%m/%Y')}",
        )
        cell.fill = day_fill
        cell.font = day_font
        cell.alignment = center
        cell.border = border
        ws.merge_cells(
            f"{get_column_letter(start_col)}{SINGLE_SHEET_HEADER_ROW_DAY}:"
            f"{get_column_letter(end_col)}{SINGLE_SHEET_HEADER_ROW_DAY}"
        )

    for c_idx, title in enumerate(BASE_HEADERS, start=1):
        cell = ws.cell(row=SINGLE_SHEET_HEADER_ROW_FIELDS, column=c_idx, value=title)
        cell.fill = header_fill
        cell.font = header_font
        cell.alignment = center
        cell.border = border

    for day_idx in range(DAY_COUNT):
        for f_idx, title in enumerate(DAY_FIELD_HEADERS):
            col = single_sheet_day_col(day_idx, f_idx)
            cell = ws.cell(row=SINGLE_SHEET_HEADER_ROW_FIELDS, column=col, value=title)
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = center
            cell.border = border

    start_row = SINGLE_SHEET_DATA_START_ROW
    for i, emp in enumerate(employees, start=start_row):
        ws.cell(row=i, column=1, value=str(emp.get("afm") or ""))
        ws.cell(row=i, column=2, value=str(emp.get("eponymo") or ""))
        ws.cell(row=i, column=3, value=str(emp.get("onoma") or ""))
        for c in range(1, last_col + 1):
            cell = ws.cell(row=i, column=c)
            cell.border = border
            cell.alignment = center
        for day_idx in range(DAY_COUNT):
            for f_idx in (1, 2, 3, 4):
                col = single_sheet_day_col(day_idx, f_idx)
                ws.cell(row=i, column=col).number_format = "hh:mm"

    max_row = start_row + len(employees) - 1 if employees else start_row

    for day_idx in range(DAY_COUNT):
        energia_col = get_column_letter(single_sheet_day_col(day_idx, 0))
        dv_action = DataValidation(
            type="list", formula1='"ΡΕΠΟ"', allow_blank=True, showDropDown=False
        )
        dv_action.errorTitle = "Μη έγκυρη τιμή"
        dv_action.error = "Επιτρέπεται μόνο ΡΕΠΟ ή κενό."
        ws.add_data_validation(dv_action)
        if employees:
            dv_action.add(f"{energia_col}{start_row}:{energia_col}{max_row}")

        dv_time = DataValidation(type="time", allow_blank=True)
        dv_time.errorTitle = "Μη έγκυρη ώρα"
        dv_time.error = "Δώσε ώρα σε μορφή ΩΩ:ΛΛ (π.χ. 09:00)."
        ws.add_data_validation(dv_time)
        for f_idx in (1, 2, 3, 4):
            col = get_column_letter(single_sheet_day_col(day_idx, f_idx))
            if employees:
                dv_time.add(f"{col}{start_row}:{col}{max_row}")

    ws.column_dimensions["A"].width = 14
    ws.column_dimensions["B"].width = 22
    ws.column_dimensions["C"].width = 18
    for day_idx in range(DAY_COUNT):
        for f_idx, width in enumerate((11, 9, 9, 9, 9)):
            col = get_column_letter(single_sheet_day_col(day_idx, f_idx))
            ws.column_dimensions[col].width = width

    ws.freeze_panes = f"A{start_row}"
    if employees:
        ws.auto_filter.ref = f"A{SINGLE_SHEET_HEADER_ROW_FIELDS}:{last_letter}{max_row}"

    bio = BytesIO()
    wb.save(bio)
    store_part = _safe_filename_part(str(store.get("name") or f"store_{store_id}"))
    filename = (
        f"weekly_schedule_{store_part}_"
        f"{week_monday.strftime('%Y%m%d')}_{sunday.strftime('%Y%m%d')}.xlsx"
    )
    meta = {
        "week_from": week_monday.strftime("%d/%m/%Y"),
        "week_to": sunday.strftime("%d/%m/%Y"),
        "employee_count": str(len(employees)),
    }
    return bio.getvalue(), filename, meta
