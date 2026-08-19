"""Excel export for calculated retrospective timekeeping."""

from __future__ import annotations

from io import BytesIO
from typing import Any

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter


_NAVY = "17324D"
_BLUE = "2F75B5"
_LIGHT = "EAF2F8"
_BORDER = Side(style="thin", color="D9E2E9")


def _duration(minutes: Any) -> float:
    return max(0, int(minutes or 0)) / 1440


def _style_sheet(ws, *, title: str, meta: str, headers: list[str], widths: list[int]) -> int:
    ws.sheet_view.showGridLines = False
    ws.append([title])
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(headers))
    ws["A1"].font = Font(name="Aptos Display", size=18, bold=True, color="FFFFFF")
    ws["A1"].fill = PatternFill("solid", fgColor=_NAVY)
    ws["A1"].alignment = Alignment(vertical="center")
    ws.row_dimensions[1].height = 30
    ws.append([meta])
    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=len(headers))
    ws["A2"].font = Font(name="Aptos", size=10, color="526777")
    ws.append(headers)
    header_row = 3
    for cell in ws[header_row]:
        cell.font = Font(name="Aptos", size=10, bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor=_BLUE)
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = Border(bottom=_BORDER)
    ws.row_dimensions[header_row].height = 34
    for index, width in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(index)].width = width
    ws.freeze_panes = "A4"
    return header_row


def _finish_table(ws, header_row: int, duration_from: int, duration_to: int) -> None:
    if ws.max_row > header_row:
        ws.auto_filter.ref = f"A{header_row}:{get_column_letter(ws.max_column)}{ws.max_row}"
    for row in range(header_row + 1, ws.max_row + 1):
        if row % 2 == 0:
            for cell in ws[row]:
                cell.fill = PatternFill("solid", fgColor=_LIGHT)
        for col in range(duration_from, duration_to + 1):
            ws.cell(row, col).number_format = "[h]:mm"
            ws.cell(row, col).alignment = Alignment(horizontal="right")
        for cell in ws[row]:
            cell.border = Border(bottom=_BORDER)
            cell.font = Font(name="Aptos", size=10)
            cell.alignment = Alignment(vertical="top", wrap_text=cell.column in (1, ws.max_column))


def build_timekeeping_export_xlsx(*, report: dict[str, Any], meta_line: str) -> bytes:
    wb = Workbook()
    summary = wb.active
    summary.title = "Σύνοψη"
    summary_headers = [
        "Εργαζόμενος", "ΑΦΜ", "Αναγνωρισμένη βάση", "Ημέρα", "Νύχτα 25%",
        "Κυρ/Αργία 75%", "Νύχτα + Κυρ/Αργία", "Μερική 12%",
        "6η ημέρα 30%", "Υπερωρία 40%", "Υπερωρία 60%", "120%",
        "Ετήσιες νόμιμες υπερωρίες μετά την περίοδο",
    ]
    header_row = _style_sheet(
        summary, title="Ωρομέτρηση εβδομάδας", meta=meta_line,
        headers=summary_headers, widths=[28, 14, 20, 14, 16, 20, 22, 16, 17, 17, 17, 14, 25],
    )
    for item in report.get("employees") or []:
        summary.append([
            f"{item.get('eponymo') or ''} {item.get('onoma') or ''}".strip(),
            str(item.get("employee_afm") or ""),
            _duration(item.get("recognized_work_minutes")), _duration(item.get("day")),
            _duration(item.get("night")), _duration(item.get("sunday_holiday")),
            _duration(item.get("night_sunday_holiday")), _duration(item.get("partial_additional_12")),
            _duration(item.get("sixth_day_minutes")), _duration(item.get("overtime_40")),
            _duration(item.get("overtime_60")),
            _duration(int(item.get("overtime_120") or 0) + int(item.get("partial_120") or 0)),
            _duration(item.get("annual_legal_overtime_minutes_after_period")),
        ])
    _finish_table(summary, header_row, 3, len(summary_headers))
    summary.column_dimensions["B"].number_format = "@"

    daily = wb.create_sheet("Ανά ημέρα")
    daily_headers = [
        "Ημερομηνία", "Εργαζόμενος", "ΑΦΜ", "Κατάσταση", "Πηγή βάσης",
        "Αναγνωρισμένο ωράριο", "Διάλειμμα", "Καθαρή βάση", "Ημέρα", "Νύχτα 25%",
        "Κυρ/Αργία 75%", "Νύχτα + Κυρ/Αργία", "Μερική 12%", "6η ημέρα 30%",
        "Υπερωρία 40%", "Υπερωρία 60%", "120%", "Παρατηρήσεις",
    ]
    daily_header = _style_sheet(
        daily, title="Αναλυτική ωρομέτρηση ανά ημέρα", meta=meta_line,
        headers=daily_headers,
        widths=[14, 28, 14, 12, 22, 24, 18, 16, 14, 16, 20, 22, 16, 17, 17, 17, 14, 46],
    )
    for item in report.get("days") or []:
        premiums = item.get("premium_minutes") or {}
        daily.append([
            item.get("work_date") or "",
            f"{item.get('eponymo') or ''} {item.get('onoma') or ''}".strip(),
            str(item.get("employee_afm") or ""), item.get("status") or "",
            item.get("basis_source") or "", item.get("basis_label") or "",
            item.get("break_interval") or "", _duration(item.get("recognized_work_minutes")),
            _duration(premiums.get("day")), _duration(premiums.get("night")),
            _duration(premiums.get("sunday_holiday")), _duration(premiums.get("night_sunday_holiday")),
            _duration(item.get("partial_additional_12")), _duration(item.get("sixth_day_minutes")),
            _duration(item.get("overtime_40")), _duration(item.get("overtime_60")),
            _duration(int(item.get("overtime_120") or 0) + int(item.get("partial_120") or 0)),
            " · ".join(str(value) for value in item.get("warnings") or []),
        ])
    _finish_table(daily, daily_header, 8, 17)

    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()
