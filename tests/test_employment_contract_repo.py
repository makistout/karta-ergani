"""Tests για hash / σύγκριση στοιχείων σύμβασης."""

from __future__ import annotations

from typing import Any

from app.repo_employment_contract import (
    _normalize_row,
    content_hash_for_contract,
    contract_terms_hash,
)


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


def test_keeper_prefers_current_then_newest_id():
    from app.repo_employment_contract import _keeper_id_for_equivalent_rows

    assert _keeper_id_for_equivalent_rows([
        {"id": 10, "is_current": 0},
        {"id": 20, "is_current": 1},
        {"id": 30, "is_current": 0},
    ]) == 20
    assert _keeper_id_for_equivalent_rows([
        {"id": 10, "is_current": 0},
        {"id": 30, "is_current": 0},
    ]) == 30


def test_content_hash_treats_portal_labels_and_api_codes_as_same():
    portal = {
        "specialty": "ΑΠΟΘΗΚΑΡΙΟΣ",
        "characterization": "ΕΡΓΑΤΗΣ",
        "step92": "ΑΠΟΘΗΚΑΡΙΟΙ",
        "weekly_work_days": "5-ήμερη",
        "employment_relation": "ΑΟΡΙΣΤΟΥ ΧΡΟΝΟΥ",
        "regime": "ΜΕΡΙΚΗ",
        "weekly_hours": "20,0",
        "salary": "534,17",
        "hourly_wage": "6,16",
        "fulltime_contract_weekly_hours": "40,0",
        "ergani_updated_at": "10/09/2026 00:00",
    }
    api = {
        **portal,
        "characterization": "0",
        "step92": "413101-ΑΠΟΘΗΚΑΡΙΟΙ",
        "weekly_work_days": "5",
        "employment_relation": "0",
        "regime": "1",
        "weekly_hours": "20.0",
        "salary": "534.17",
        "hourly_wage": "6.16",
        "fulltime_contract_weekly_hours": "40.0",
    }
    assert content_hash_for_contract(portal) == content_hash_for_contract(api)
    assert contract_terms_hash(portal) == contract_terms_hash(api)
    assert contract_terms_hash({**portal, "arithmos_teknon": None}) == contract_terms_hash(
        {**portal, "arithmos_teknon": "0", "marital_status": "0"}
    )
    assert contract_terms_hash(portal) == contract_terms_hash(
        {**portal, "kyria_asfalish": "001"}
    )
    assert contract_terms_hash({**portal, "break_in_work": None}) == contract_terms_hash(
        {**portal, "break_in_work": 0}
    )
    assert contract_terms_hash({**portal, "total_weekly_hours": None}) == contract_terms_hash(
        {**portal, "total_weekly_hours": "20,0"}
    )
    assert contract_terms_hash(
        {**portal, "ergani_updated_at": "10/09/2026 00:00"}
    ) == contract_terms_hash(
        {**portal, "ergani_updated_at": "23/09/2026 00:00"}
    )


def test_insert_skips_when_only_encoding_differs(monkeypatch):
    portal = {
        "employee_afm": "143980812",
        "characterization": "ΕΡΓΑΤΗΣ",
        "step92": "ΑΠΟΘΗΚΑΡΙΟΙ",
        "weekly_work_days": "5-ήμερη",
        "employment_relation": "ΑΟΡΙΣΤΟΥ ΧΡΟΝΟΥ",
        "regime": "ΜΕΡΙΚΗ",
        "weekly_hours": "20,0",
        "salary": "534,17",
        "hourly_wage": "6,16",
        "fulltime_contract_weekly_hours": "40,0",
    }
    previous = {"id": 17, **_normalize_row("082136041", "0", portal)}
    repo, cur = _mock_contract_db(monkeypatch, previous)
    result = repo.insert_if_changed(
        "082136041",
        "0",
        {
            "employee_afm": "143980812",
            "characterization": "0",
            "step92": "413101-ΑΠΟΘΗΚΑΡΙΟΙ",
            "weekly_work_days": "5",
            "employment_relation": "0",
            "regime": "1",
            "weekly_hours": "20.0",
            "salary": "534.17",
            "hourly_wage": "6.16",
            "fulltime_contract_weekly_hours": "40.0",
        },
    )
    assert result == {"inserted": False, "reason": "unchanged", "id": 17}
    cur.execute.assert_called_once()


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
    assert content_hash_for_contract({**base, "arithmos_teknon": "2"}) != h0
    assert content_hash_for_contract({**base, "marital_status": "1"}) != h0
    assert content_hash_for_contract({**base, "epikourikiki_kod": "002"}) != h0
    assert content_hash_for_contract({**base, "kyria_asfalish": "002"}) != h0


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


def test_insert_keeps_family_fields_when_portal_omits_them(monkeypatch):
    previous_row = {
        "employee_afm": "141320107",
        "salary": "1000",
        "arithmos_teknon": "2",
        "marital_status": "1",
        "prior_service": "5",
    }
    previous = {
        "id": 17,
        **_normalize_row("802788173", "0", previous_row),
    }
    repo, cur = _mock_contract_db(monkeypatch, previous)
    result = repo.insert_if_changed(
        "802788173", "0", {"employee_afm": "141320107", "salary": "1000"}
    )
    assert result == {"inserted": False, "reason": "unchanged", "id": 17}
    cur.execute.assert_called_once()


def test_insert_records_family_change_from_ergani(monkeypatch):
    previous_row = {
        "employee_afm": "141320107",
        "salary": "1000",
        "arithmos_teknon": "2",
        "marital_status": "1",
    }
    previous = {"id": 17, **_normalize_row("802788173", "0", previous_row)}
    repo, cur = _mock_contract_db(monkeypatch, previous)
    result = repo.insert_if_changed(
        "802788173",
        "0",
        {"employee_afm": "141320107", "salary": "1000", "arithmos_teknon": "3"},
    )
    assert result == {"inserted": False, "reason": "unchanged", "id": 17}
    sql, params = cur.execute.call_args.args
    assert "arithmos_teknon = ?" in sql
    assert params[0] == "3"


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


def test_refresh_personal_from_ex_base_05_skips_without_api_user():
    from app.repo_employment_contract import refresh_personal_from_ex_base_05

    result = refresh_personal_from_ex_base_05({
        "username": "portal-admin",
        "password": "portal-pass",
        "employer_afm": "123456789",
    })
    assert result["success"] is False
    assert result["skipped"] is True
    assert result["detail"] == "no_api_user"


def test_refresh_personal_from_ex_base_05_uses_web_api_without_request(monkeypatch):
    from app.repo_employment_contract import refresh_personal_from_ex_base_05

    calls: dict[str, Any] = {}

    class AuthResp:
        ok = True
        status_code = 200

    class SvcResp:
        ok = True
        status_code = 200

    class FakeClient:
        def authenticate(self, user, pwd, ut):
            calls["auth"] = (user, pwd, ut)
            return AuthResp()

        def execute_service(self, name, params, bearer):
            calls["service"] = (name, list(params), bearer)
            return SvcResp()

    def fake_json(resp):
        if isinstance(resp, AuthResp):
            return {"accessToken": "tok-05"}
        return {"data": {"EX_BASE_05": {"Cur": [{"Afm": "111111111"}]}}}

    monkeypatch.setattr("app.ergani_env.client_for_store", lambda ctx: FakeClient())
    monkeypatch.setattr("app.http_helpers.json_or_text", fake_json)
    monkeypatch.setattr(
        "app.repo_employment_contract.apply_ex_base_05_items",
        lambda *args, **kwargs: {"scanned": 1, "inserted": 0, "errors": 0},
    )

    result = refresh_personal_from_ex_base_05({
        "id": 1,
        "name": "test",
        "employer_afm": "123456789",
        "branch_aa": "0",
        "username": "",
        "password": "",
        "web_username": "api-user",
        "web_password": "api-pass",
        "ergani_env": "production",
        "api_base_url": "https://example.test/",
    })
    assert result["success"] is True
    assert result["scanned"] == 1
    assert calls["auth"] == ("api-user", "api-pass", "02")
    assert calls["service"][0] == "EX_BASE_05"
    assert calls["service"][2] == "tok-05"
