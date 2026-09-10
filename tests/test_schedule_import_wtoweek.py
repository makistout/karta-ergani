from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

from app.schedule_excel_import import _read_instructions
from app.schedule_import_service import (
    _ergani_weekday,
    _snapshot_to_week_entries,
    apply_import_employee_week,
)


class _FakeCell:
    def __init__(self, value):
        self.value = value


class _FakeWs:
    def __init__(self, mapping: dict[str, object], max_row: int = 20):
        self._mapping = mapping
        self.max_row = max_row

    def __getitem__(self, key: str):
        return _FakeCell(self._mapping.get(key))

    def cell(self, row: int, column: int):
        letter = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"[column - 1]
        return _FakeCell(self._mapping.get(f"{letter}{row}"))


def test_read_instructions_by_label_not_fixed_rows():
    ws = _FakeWs({
        "A2": "Εβδομάδα 10/09/2026 - 16/09/2026",
        "A17": "Store ID",
        "B17": 11,
        "A18": "Employer AFM",
        "B18": "998402570",
        "A19": "Branch AA",
        "B19": "0",
    })
    meta = _read_instructions(ws)
    assert meta["store_id"] == 11
    assert meta["employer_afm"] == "998402570"
    assert meta["branch_aa"] == "0"
    assert meta["week_from"] == "10/09/2026"


def test_ergani_weekday_mapping():
    assert _ergani_weekday("10/09/2026") == 4  # Thursday
    assert _ergani_weekday("13/09/2026") == 0  # Sunday
    assert _ergani_weekday("14/09/2026") == 1  # Monday


def test_snapshot_to_week_entries_rest_and_split():
    assert _snapshot_to_week_entries([]) == [{"type": "ΜΕ"}]
    assert _snapshot_to_week_entries([{"schedule_type": "ΑΝ"}]) == [{"type": "ΑΝ"}]
    assert _snapshot_to_week_entries([{"shift_type": "ΜΗ ΕΡΓΑΣΙΑ"}]) == [{"type": "ΜΕ"}]
    assert _snapshot_to_week_entries([
        {"hour_from": "10:00", "hour_to": "14:00"},
        {"hour_from": "20:30", "hour_to": "23:30"},
    ]) == [
        {"type": "ΕΡΓ", "from": "10:00", "to": "14:00"},
        {"type": "ΕΡΓ", "from": "20:30", "to": "23:30"},
    ]
    assert _snapshot_to_week_entries([{"hour_from": None, "hour_to": None}]) == [{"type": "ΜΕ"}]


def test_apply_import_employee_week_one_protocol_for_all_days():
    week_dates = [
        "10/09/2026", "11/09/2026", "12/09/2026", "13/09/2026",
        "14/09/2026", "15/09/2026", "16/09/2026",
    ]
    employee_rows = []
    for idx, work_date in enumerate(week_dates, start=1):
        employee_rows.append({
            "id": idx,
            "employee_afm": "113818601",
            "eponymo": "ΓΙΑΤΡΑΣ",
            "onoma": "ΒΑΣΙΛΕΙΟΣ",
            "work_date": work_date,
            "import_action": "work" if idx <= 2 else "skip",
            "change_kind": "update" if idx <= 2 else "skip",
            "proposed_snapshot": [{"hour_from": "10:00", "hour_to": "14:00"}],
            "current_snapshot": [{"hour_from": "09:00", "hour_to": "17:00"}],
            "validation_errors": [],
        })
    apply_rows = employee_rows[:2]
    ctx = {"id": 11, "employer_afm": "998402570", "branch_aa": "0", "api_base_url": "https://example.invalid/"}

    fake_resp = MagicMock(ok=True, status_code=200)
    with patch("app.schedule_import_service.ErganiClient") as client_cls, \
         patch("app.schedule_import_service.persist_safe"), \
         patch("app.schedule_import_service._persist_local_schedule_after_wto_daily", return_value=True), \
         patch("app.schedule_import_service._current_schedule_snapshot", return_value=[]), \
         patch("app.schedule_import_service.record_wto_daily_schedule_audit"), \
         patch("app.schedule_import_service.upsert_employee"), \
         patch("app.schedule_import_service.cursor"):
        client_cls.return_value.document_submit.return_value = fake_resp
        with patch("app.schedule_import_service.json_or_text", return_value=[{"protocol": "W-1", "submitDate": "10/09/2026", "id": 9}]):
            result = apply_import_employee_week(
                ctx,
                employee_rows=employee_rows,
                apply_rows=apply_rows,
                bearer="token",
                batch_meta={"batch_id": 1},
            )

    assert result["success"] is True
    assert result["protocol"] == "W-1"
    assert result["apply_row_ids"] == [1, 2]
    submit = client_cls.return_value.document_submit
    assert submit.call_count == 1
    code, payload, bearer = submit.call_args.args
    assert code == "WTOWeek"
    assert bearer == "token"
    rows = payload["WTOS"]["WTO"][0]["Ergazomenoi"]["ErgazomenoiWTO"]
    assert len(rows) == 7
    assert {row["f_day"] for row in rows} == {"0", "1", "2", "3", "4", "5", "6"}
