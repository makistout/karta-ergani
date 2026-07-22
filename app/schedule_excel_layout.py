"""Κοινή διάταξη Excel εβδομαδιαίου ωραρίου (ένα φύλλο, 7 ημέρες × 2 διαστήματα)."""

from __future__ import annotations

WEEK_SHEET = "Εβδομάδα"
INSTRUCTIONS_SHEET = "Οδηγίες"

BASE_HEADERS = ["ΑΦΜ", "Επώνυμο", "Όνομα"]
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

# Legacy: ένα φύλλο ανά ημέρα (8 στήλες)
LEGACY_DAY_HEADERS = BASE_HEADERS + LEGACY_WIDE_DAY_HEADERS


def single_sheet_day_col(
    day_index: int,
    field_offset: int = 0,
    *,
    fields_per_day: int | None = None,
) -> int:
    """1-based στήλη Excel: day_index 0=Δευτέρα, field_offset 0=Ενέργεια …"""
    n = DAY_FIELD_COUNT if fields_per_day is None else int(fields_per_day)
    return BASE_COL_COUNT + day_index * n + field_offset + 1


def single_sheet_last_col(*, fields_per_day: int | None = None) -> int:
    n = DAY_FIELD_COUNT if fields_per_day is None else int(fields_per_day)
    return BASE_COL_COUNT + DAY_COUNT * n


def employee_block_start_row(emp_index: int) -> int:
    """1-based πρώτη γραμμή δεδομένων για εργαζόμενο (0-based index)."""
    return SINGLE_SHEET_DATA_START_ROW + int(emp_index) * ROWS_PER_EMPLOYEE
