"""Tests για αρχειοθέτηση Excel portal (τρέχουσα ημέρα)."""

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from app.portal_excel_archive import PortalExcelArchive, range_includes_today


def test_range_includes_today_single_day():
    today = datetime.now(ZoneInfo("Europe/Athens")).strftime("%d/%m/%Y")
    assert range_includes_today(today, today) is True


def test_range_includes_today_past_only():
    assert range_includes_today("01/01/2020", "02/01/2020") is False


def test_portal_excel_archive_writes_xlsx_and_meta(tmp_path, monkeypatch):
    monkeypatch.setattr(
        "app.portal_excel_archive.Config.KARTA_PORTAL_EXCEL_DEBUG_TODAY",
        True,
    )
    monkeypatch.setattr(
        "app.portal_excel_archive.Config.PORTAL_EXCEL_DEBUG_DIR",
        tmp_path,
    )
    archive = PortalExcelArchive(
        kind="work_log",
        store_id=4,
        store_name="Training Room",
        employer_afm="803072758",
        branch_aa="0",
        date_from="27/06/2026",
        date_to="27/06/2026",
        run_id="653bfd13-abcd",
    )
    content = b"PK\x03\x04fake-xlsx"
    path = archive.record_excel(content, "application/vnd.openxmlformats", row_count=0)
    assert path is not None
    assert path.exists()
    meta = Path(str(path) + ".meta.json")
    assert meta.exists()
    assert "row_count" in meta.read_text(encoding="utf-8")
