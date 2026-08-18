"""Κοινή διάταξη Excel εβδομαδιαίου ωραρίου (ένα φύλλο, 7 ημέρες × 2 διαστήματα)."""

from __future__ import annotations

import re
from typing import Any

WEEK_SHEET = "Εβδομάδα"
INSTRUCTIONS_SHEET = "Οδηγίες"

IDENTITY_HEADERS = ["ΑΦΜ", "Επώνυμο", "Όνομα"]
HOURS_HEADER = "Ώρες"
BASE_HEADERS = IDENTITY_HEADERS + [HOURS_HEADER]
HOURS_COL = len(IDENTITY_HEADERS) + 1
LEGACY_BASE_COL_COUNT = len(IDENTITY_HEADERS)
# Νέο format: 3 στήλες/ημέρα · 2 γραμμές/εργαζόμενο (πάνω=διάστημα1, κάτω=διάστημα2).
DAY_FIELD_HEADERS = ["Ενέργεια", "Από", "Έως"]
DAY_FIELD_COUNT = len(DAY_FIELD_HEADERS)
BASE_COL_COUNT = len(BASE_HEADERS)
DAY_COUNT = 7
ROWS_PER_EMPLOYEE = 2

# Παλιό single-sheet: 5 στήλες/ημέρα σε μία γραμμή (Από1…Έως2).
LEGACY_WIDE_DAY_HEADERS = ["Ενέργεια", "Από1", "Έως1", "Από2", "Έως2"]
LEGACY_WIDE_DAY_FIELD_COUNT = len(LEGACY_WIDE_DAY_HEADERS)

SINGLE_SHEET_HEADER_ROW_DAY = 3
SINGLE_SHEET_HEADER_ROW_FIELDS = 4
SINGLE_SHEET_DATA_START_ROW = 5

# Legacy: ένα φύλλο ανά ημέρα (8 στήλες) — χωρίς στήλη Ώρες.
LEGACY_DAY_HEADERS = IDENTITY_HEADERS + LEGACY_WIDE_DAY_HEADERS

_HM = re.compile(r"^(\d{1,2}):(\d{2})")


def single_sheet_day_col(
    day_index: int,
    field_offset: int = 0,
    *,
    fields_per_day: int | None = None,
    base_col_count: int | None = None,
) -> int:
    """1-based στήλη Excel: day_index 0=Δευτέρα, field_offset 0=Ενέργεια …"""
    n = DAY_FIELD_COUNT if fields_per_day is None else int(fields_per_day)
    base = BASE_COL_COUNT if base_col_count is None else int(base_col_count)
    return base + day_index * n + field_offset + 1


def single_sheet_last_col(
    *,
    fields_per_day: int | None = None,
    base_col_count: int | None = None,
) -> int:
    n = DAY_FIELD_COUNT if fields_per_day is None else int(fields_per_day)
    base = BASE_COL_COUNT if base_col_count is None else int(base_col_count)
    return base + DAY_COUNT * n


def employee_block_start_row(emp_index: int) -> int:
    """1-based πρώτη γραμμή δεδομένων για εργαζόμενο (0-based index)."""
    return SINGLE_SHEET_DATA_START_ROW + int(emp_index) * ROWS_PER_EMPLOYEE


def base_col_count_from_header(col4_header: str | None) -> int:
    """Νέα αρχεία έχουν «Ώρες» στη στήλη 4· παλιά ξεκινούν τις ημέρες εκεί."""
    return BASE_COL_COUNT if str(col4_header or "").strip() == HOURS_HEADER else LEGACY_BASE_COL_COUNT


def hm_to_minutes(value: str | None) -> int | None:
    m = _HM.match(str(value or "").strip())
    if not m:
        return None
    h, minutes = int(m.group(1)), int(m.group(2))
    if h > 23 or minutes > 59:
        return None
    return h * 60 + minutes


def interval_minutes(hour_from: str | None, hour_to: str | None) -> int:
    start = hm_to_minutes(hour_from)
    end = hm_to_minutes(hour_to)
    if start is None or end is None:
        return 0
    duration = end - start
    if duration < 0:
        duration += 24 * 60
    return duration if duration > 0 else 0


def shift_counts_as_work(shift_type: str | None) -> bool:
    shift = str(shift_type or "").strip().upper()
    if not shift:
        return True
    if shift in {"ΑΝ", "AN", "Ρ", "ΡΕΠΟ", "ΜΕ"}:
        return False
    if "ΡΕΠΟ" in shift or "ΑΝΑΠΑΥΣ" in shift or "ΑΔΕΙΑ" in shift:
        return False
    if shift.startswith("AD"):
        return False
    return True


def weekly_declared_minutes(rows: list[dict[str, Any]] | None) -> int:
    total = 0
    for row in rows or []:
        if not shift_counts_as_work(row.get("shift_type")):
            continue
        total += interval_minutes(row.get("hour_from"), row.get("hour_to"))
    return total


def format_hours_minutes(total_minutes: int) -> str:
    hours, minutes = divmod(max(0, int(total_minutes or 0)), 60)
    return f"{hours}:{minutes:02d}"
