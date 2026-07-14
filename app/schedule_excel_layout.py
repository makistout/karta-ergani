"""Κοινή διάταξη Excel εβδομαδιαίου ωραρίου (ένα φύλλο, 7 ημέρες × 2 διαστήματα)."""

from __future__ import annotations

WEEK_SHEET = "Εβδομάδα"
INSTRUCTIONS_SHEET = "Οδηγίες"

BASE_HEADERS = ["ΑΦΜ", "Επώνυμο", "Όνομα"]
DAY_FIELD_HEADERS = ["Ενέργεια", "Από1", "Έως1", "Από2", "Έως2"]
DAY_FIELD_COUNT = len(DAY_FIELD_HEADERS)
BASE_COL_COUNT = len(BASE_HEADERS)
DAY_COUNT = 7

SINGLE_SHEET_HEADER_ROW_DAY = 3
SINGLE_SHEET_HEADER_ROW_FIELDS = 4
SINGLE_SHEET_DATA_START_ROW = 5

# Legacy: ένα φύλλο ανά ημέρα (8 στήλες)
LEGACY_DAY_HEADERS = BASE_HEADERS + DAY_FIELD_HEADERS


def single_sheet_day_col(day_index: int, field_offset: int = 0) -> int:
    """1-based στήλη Excel: day_index 0=Δευτέρα, field_offset 0=Ενέργεια … 4=Έως2."""
    return BASE_COL_COUNT + day_index * DAY_FIELD_COUNT + field_offset + 1


def single_sheet_last_col() -> int:
    return BASE_COL_COUNT + DAY_COUNT * DAY_FIELD_COUNT
