"""Tests για hash / σύγκριση στοιχείων σύμβασης."""

from __future__ import annotations

from app.repo_employment_contract import content_hash_for_contract, _normalize_row


def test_content_hash_stable_for_same_fields():
    row = {
        "specialty": "ΣΕΡΒΙΤΟΡΟΣ",
        "characterization": "Α",
        "step92": "5131",
        "weekly_work_days": "6",
        "prior_service": "0",
        "employment_relation": "ΑΟΡΙΣΤΟΥ",
        "fixed_term_from": "",
        "fixed_term_to": "",
        "regime": "ΠΛΗΡΗΣ",
        "weekly_hours": "40",
        "salary": "1000",
        "hourly_wage": "",
        "total_weekly_hours": "40",
        "fulltime_contract_weekly_hours": "40",
        "break_minutes": 30,
        "break_in_work": 1,
        "flex_arrival_minutes": 120,
        "ergani_updated_at": "01/06/2026",
    }
    h1 = content_hash_for_contract(row)
    h2 = content_hash_for_contract({**row, "specialty": " ΣΕΡΒΙΤΟΡΟΣ "})
    assert h1 == h2
    assert len(h1) == 64


def test_content_hash_changes_on_field_or_ergani_date():
    base = {
        "specialty": "ΣΕΡΒΙΤΟΡΟΣ",
        "ergani_updated_at": "01/06/2026",
        "weekly_hours": "40",
        "flex_arrival_minutes": 120,
    }
    h0 = content_hash_for_contract(base)
    assert content_hash_for_contract({**base, "weekly_hours": "35"}) != h0
    assert content_hash_for_contract({**base, "ergani_updated_at": "02/06/2026"}) != h0


def test_normalize_row_keys_employer_branch_employee():
    data = _normalize_row(
        "802788173",
        "0",
        {
            "employee_afm": "141320107",
            "eponymo": "LUNGOLOVA",
            "onoma": "VERGINIYA",
            "specialty": "ΜΑΓΕΙΡΑΣ",
            "flex_arrival_minutes": "120",
            "break_in_work": "1",
        },
    )
    assert data["employer_afm"] == "802788173"
    assert data["branch_aa"] == "0"
    assert data["employee_afm"] == "141320107"
    assert data["flex_arrival_minutes"] == 120
    assert data["break_in_work"] == 1
    assert data["content_hash"]


def _mock_contract_db(monkeypatch, previous):
    from contextlib import contextmanager
    from unittest.mock import MagicMock
    from app import repo_employment_contract as repo

    cur = MagicMock()
    cur.fetchone.return_value = (42,)

    @contextmanager
    def fake_cursor(**kwargs):
        yield cur

    monkeypatch.setattr(repo, "cursor", fake_cursor)
    monkeypatch.setattr(repo, "latest_for_employee", lambda *args: previous)
    return repo, cur


def test_unchanged_contract_refreshes_check_without_new_snapshot(monkeypatch):
    row = {"employee_afm": "141320107", "salary": "1000"}
    previous = {"id": 17, "content_hash": _normalize_row("802788173", "0", row)["content_hash"]}
    repo, cur = _mock_contract_db(monkeypatch, previous)

    result = repo.insert_if_changed("802788173", "0", row)

    assert result == {"inserted": False, "reason": "unchanged", "id": 17}
    cur.execute.assert_called_once()
    sql, params = cur.execute.call_args.args
    assert "SET last_checked_at = SYSDATETIMEOFFSET()" in sql
    assert "WHERE id = ? AND is_current = 1" in sql
    assert params == (17,)
    assert "synced_at" not in sql


def test_changed_contract_records_check_on_new_snapshot(monkeypatch):
    repo, cur = _mock_contract_db(monkeypatch, {"id": 17, "content_hash": "old"})
    result = repo.insert_if_changed("802788173", "0", {"employee_afm": "141320107", "salary": "1100"})

    assert result["inserted"] is True
    assert result["id"] == 42
    assert cur.execute.call_count == 2
    archive_sql = cur.execute.call_args_list[0].args[0]
    assert "SET is_current = 0" in archive_sql
    assert "last_checked_at" not in archive_sql
    insert_sql = cur.execute.call_args_list[1].args[0]
    assert "last_checked_at" in insert_sql
    assert "SYSDATETIMEOFFSET()" in insert_sql


def test_first_contract_records_successful_check(monkeypatch):
    repo, cur = _mock_contract_db(monkeypatch, None)
    result = repo.insert_if_changed("802788173", "0", {"employee_afm": "141320107"})
    assert result["inserted"] is True
    cur.execute.assert_called_once()
    assert "last_checked_at" in cur.execute.call_args.args[0]


def test_check_timestamp_does_not_change_contract_hash():
    row = {"salary": "1000"}
    assert content_hash_for_contract(row) == content_hash_for_contract({**row, "last_checked_at": "2026-09-07"})
