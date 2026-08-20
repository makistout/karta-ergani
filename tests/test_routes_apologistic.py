from datetime import date

from flask import Flask

from app import routes_apologistic


def _app():
    app = Flask(__name__)
    app.register_blueprint(routes_apologistic.apologistic_bp)
    return app


def _store():
    return {"id": 12, "name": "Store", "employer_afm": "012345678", "branch_aa": "0"}


def test_current_week_is_rejected_before_database_read(monkeypatch):
    monkeypatch.setattr(routes_apologistic, "resolve_active_store", _store)
    monkeypatch.setattr(routes_apologistic, "previous_week", lambda: (date(2026, 8, 3), date(2026, 8, 9)))
    monkeypatch.setattr(routes_apologistic, "load_report", lambda *_: (_ for _ in ()).throw(AssertionError("database must not be read")))
    response = _app().test_client().get("/api/apologistic/week?from=2026-08-10&to=2026-08-16")
    assert response.status_code == 400


def test_existing_week_is_returned_from_database(monkeypatch):
    monkeypatch.setattr(routes_apologistic, "resolve_active_store", _store)
    monkeypatch.setattr(routes_apologistic, "previous_week", lambda: (date(2026, 8, 3), date(2026, 8, 9)))
    monkeypatch.setattr(routes_apologistic, "tables_available", lambda: True)
    monkeypatch.setattr(
        routes_apologistic,
        "load_report",
        lambda *_: ({"days": [], "employees": [], "counts": {"all": 0}}, {"id": 7, "status": "draft"}),
    )
    response = _app().test_client().get("/api/apologistic/week?from=2026-08-03&to=2026-08-09")
    assert response.status_code == 200
    assert response.get_json()["snapshot"]["source"] == "database"


def test_missing_past_snapshot_does_not_calculate_on_the_fly(monkeypatch):
    monkeypatch.setattr(routes_apologistic, "resolve_active_store", _store)
    monkeypatch.setattr(routes_apologistic, "previous_week", lambda: (date(2026, 8, 3), date(2026, 8, 9)))
    monkeypatch.setattr(routes_apologistic, "tables_available", lambda: True)
    monkeypatch.setattr(routes_apologistic, "load_report", lambda *_: None)
    response = _app().test_client().get("/api/apologistic/week?from=2026-07-27&to=2026-08-02")
    assert response.status_code == 404
    assert "αποθηκευμένο" in response.get_json()["error"]


def test_timekeeping_preview_uses_archive_context_and_holidays(monkeypatch):
    monkeypatch.setattr(routes_apologistic, "resolve_active_store", _store)
    monkeypatch.setattr(routes_apologistic, "load_report", lambda *_: ({"days": [{
        "employee_afm": "123456789", "work_date": "03/08/2026", "status": "ok",
        "declared": "09:00–17:00", "punch_count": 2, "overtime_minutes": 60,
    }]}, {"id": 7, "status": "draft"}))
    monkeypatch.setattr(routes_apologistic, "load_annual_overtime_context", lambda **kwargs: {
        "123456789": {"legal_overtime_minutes_before_period": 149 * 60 + 30, "data_complete": True},
    })
    monkeypatch.setattr(routes_apologistic, "get_effective_holidays_for_store", lambda *_: set())
    monkeypatch.setattr(routes_apologistic, "get_sunday_rest_transfer_enabled", lambda *_: False)
    monkeypatch.setattr(routes_apologistic, "_next_week_rest_context", lambda *_: {
        "123456789": {"known": False, "explicit_rest_days": 0},
    })
    response = _app().test_client().post(
        "/api/apologistic/timekeeping/preview", json={"week_from": "2026-08-03"},
    )
    assert response.status_code == 200
    body = response.get_json()
    assert body["preview"] is True
    assert body["days"][0]["overtime_40"] == 30
    assert body["days"][0]["overtime_60"] == 30


def test_timekeeping_preview_rejects_review_rows(monkeypatch):
    monkeypatch.setattr(routes_apologistic, "resolve_active_store", _store)
    monkeypatch.setattr(routes_apologistic, "load_report", lambda *_: ({"days": [{
        "employee_afm": "123456789", "work_date": "03/08/2026", "status": "review",
    }]}, {"id": 7}))
    response = _app().test_client().post(
        "/api/apologistic/timekeeping/preview", json={"week_from": "2026-08-03"},
    )
    assert response.status_code == 409


def test_timekeeping_preview_ignores_leave_even_when_its_apologistic_status_is_review(monkeypatch):
    monkeypatch.setattr(routes_apologistic, "resolve_active_store", _store)
    monkeypatch.setattr(routes_apologistic, "load_report", lambda *_: ({"days": [{
        "employee_afm": "123456789", "work_date": "03/08/2026", "status": "review",
        "day_state": "Άδεια", "declared": "ΑΔΕΙΑ", "proposed": "ΑΔΕΙΑ",
    }]}, {"id": 7}))
    monkeypatch.setattr(routes_apologistic, "load_annual_overtime_context", lambda **_: {})
    monkeypatch.setattr(routes_apologistic, "get_effective_holidays_for_store", lambda *_: set())
    monkeypatch.setattr(routes_apologistic, "get_sunday_rest_transfer_enabled", lambda *_: False)
    monkeypatch.setattr(routes_apologistic, "_next_week_rest_context", lambda *_: {})
    response = _app().test_client().post(
        "/api/apologistic/timekeeping/preview", json={"week_from": "2026-08-03"},
    )
    assert response.status_code == 200
    assert response.get_json()["counts"] == {"days": 0, "employees": 0}


def test_next_week_context_counts_only_explicit_rest_days(monkeypatch):
    monkeypatch.setattr(routes_apologistic, "list_schedule_for_range", lambda *_args, **_kwargs: [
        {"employee_afm": "123", "work_date": "10/08/2026", "shift_type": "ΑΝΑΠΑΥΣΗ/ΡΕΠΟ"},
        {"employee_afm": "123", "work_date": "11/08/2026", "shift_type": "ΡΕΠΟ"},
        {"employee_afm": "123", "work_date": "12/08/2026", "shift_type": "ΑΝΑΠΑΥΣΗ"},
        {"employee_afm": "123", "work_date": "13/08/2026", "shift_type": "ΑΔΕΙΑ"},
        {"employee_afm": "123", "work_date": "14/08/2026", "shift_type": "ΕΡΓΑΣΙΑ", "hour_from": "09:00", "hour_to": "17:00"},
    ])
    result = routes_apologistic._next_week_rest_context(_store(), date(2026, 8, 3), ["123", "999"])
    assert result["123"]["known"] is True
    assert result["123"]["explicit_rest_days"] == 3
    assert result["999"]["known"] is False


def test_timekeeping_month_preview_returns_merged_period(monkeypatch):
    monkeypatch.setattr(routes_apologistic, "resolve_active_store", _store)
    monkeypatch.setattr(
        routes_apologistic,
        "_build_timekeeping_for_month",
        lambda *_args, **_kwargs: (
            {"calculation_version": "timekeeping-v1-month", "employees": [], "days": [], "counts": {"days": 10, "employees": 2}},
            [{"id": 7, "week_from": "2026-08-03", "week_to": "2026-08-09", "status": "draft"}],
            {"123456789": {"legal_overtime_minutes_before_period": 120}},
        ),
    )
    response = _app().test_client().post(
        "/api/apologistic/timekeeping/preview", json={"year": 2026, "month": 8},
    )
    assert response.status_code == 200
    body = response.get_json()
    assert body["period_type"] == "month"
    assert body["period_from"] == "2026-08-01"
    assert body["period_to"] == "2026-08-31"
    assert body["counts"]["days"] == 10


def test_timekeeping_export_returns_xlsx(monkeypatch):
    monkeypatch.setattr(routes_apologistic, "resolve_active_store", _store)
    monkeypatch.setattr(routes_apologistic, "_build_timekeeping_for_week", lambda *_: ({
        "calculation_version": "timekeeping-v1", "employees": [], "days": [],
    }, {"id": 7}, {}))
    monkeypatch.setattr(routes_apologistic, "build_timekeeping_export_xlsx", lambda **kwargs: b"xlsx-bytes")
    response = _app().test_client().post(
        "/api/apologistic/timekeeping/export", json={"week_from": "2026-08-03"},
    )
    assert response.status_code == 200
    assert response.data == b"xlsx-bytes"
    assert response.headers["Content-Disposition"].endswith("orometrisi_20260803.xlsx")


def test_timekeeping_month_export_returns_xlsx(monkeypatch):
    monkeypatch.setattr(routes_apologistic, "resolve_active_store", _store)
    monkeypatch.setattr(routes_apologistic, "_build_timekeeping_for_month", lambda *_args, **_kwargs: ({
        "calculation_version": "timekeeping-v1-month", "employees": [], "days": [],
    }, [{"id": 7}], {}))
    monkeypatch.setattr(routes_apologistic, "build_timekeeping_export_xlsx", lambda **kwargs: b"xlsx-bytes")
    response = _app().test_client().post(
        "/api/apologistic/timekeeping/export", json={"year": 2026, "month": 8},
    )
    assert response.status_code == 200
    assert response.data == b"xlsx-bytes"
    assert response.headers["Content-Disposition"].endswith("orometrisi_month_202608.xlsx")


def test_timekeeping_detailed_export_returns_second_xlsx(monkeypatch):
    monkeypatch.setattr(routes_apologistic, "resolve_active_store", _store)
    monkeypatch.setattr(routes_apologistic, "_build_timekeeping_for_week", lambda *_: ({
        "calculation_version": "timekeeping-v1", "employees": [], "days": [],
    }, {"id": 7}, {}))
    monkeypatch.setattr(routes_apologistic, "build_timekeeping_detailed_export_xlsx", lambda **kwargs: b"detail-bytes")
    response = _app().test_client().post(
        "/api/apologistic/timekeeping/export-detailed", json={"week_from": "2026-08-03"},
    )
    assert response.status_code == 200
    assert response.data == b"detail-bytes"
    assert response.headers["Content-Disposition"].endswith("orometrisi_analysis_20260803.xlsx")


def test_month_returns_saved_rows_and_all_intersecting_weeks(monkeypatch):
    monkeypatch.setattr(routes_apologistic, "resolve_active_store", _store)
    monkeypatch.setattr(routes_apologistic, "previous_week", lambda: (date(2026, 8, 3), date(2026, 8, 9)))
    monkeypatch.setattr(routes_apologistic, "tables_available", lambda: True)
    monkeypatch.setattr(routes_apologistic, "list_store_days", lambda **kwargs: [{
        "employee_afm": "123456789", "work_date": "01/07/2026",
        "week_from": "2026-06-29", "week_to": "2026-07-05", "status": "ok",
    }])
    monkeypatch.setattr(routes_apologistic, "enrich_employee_month_days", lambda **kwargs: None)
    response = _app().test_client().get("/api/apologistic/month?year=2026&month=7")
    assert response.status_code == 200
    body = response.get_json()
    assert body["employees"] == ["123456789"]
    assert body["work_dates"] == ["01/07/2026"]
    assert body["weeks"][0] == {
        "from": "2026-06-29", "to": "2026-07-05",
        "visible_from": "2026-07-01", "visible_to": "2026-07-05", "available": True,
    }
    assert body["weeks"][-1]["from"] == "2026-07-27"
    assert body["weeks"][-1]["visible_to"] == "2026-07-31"


def test_range_returns_only_requested_saved_dates(monkeypatch):
    monkeypatch.setattr(routes_apologistic, "resolve_active_store", _store)
    monkeypatch.setattr(routes_apologistic, "previous_week", lambda: (date(2026, 8, 3), date(2026, 8, 9)))
    monkeypatch.setattr(routes_apologistic, "tables_available", lambda: True)
    captured = {}
    monkeypatch.setattr(routes_apologistic, "list_store_days", lambda **kwargs: captured.update(kwargs) or [])
    monkeypatch.setattr(routes_apologistic, "enrich_employee_month_days", lambda **kwargs: None)
    response = _app().test_client().get("/api/apologistic/range?from=2026-07-10&to=2026-07-22")
    assert response.status_code == 200
    assert captured["date_from"] == date(2026, 7, 10)
    assert captured["date_to"] == date(2026, 7, 22)


def test_accept_review_returns_change_from_review(monkeypatch):
    monkeypatch.setattr(routes_apologistic, "resolve_active_store", _store)
    monkeypatch.setattr(
        routes_apologistic, "accept_review",
        lambda **kwargs: {
            "status": "change",
            "change_from_review": True,
            "changed": True,
            "reason": "Εγκρίθηκε η πρόταση",
            "proposed": "09:00–17:00",
            "counts": {"review": 0, "change": 5},
        },
    )
    app = _app()
    app.secret_key = "test"
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["office_user"] = "tester"
    response = client.put("/api/apologistic/accept-review", json={
        "week_from": "2026-08-03", "work_date": "04/08/2026", "employee_afm": "123456789",
    })
    assert response.status_code == 200
    body = response.get_json()
    assert body["change_from_review"] is True
    assert body["status"] == "change"


def test_restore_review_returns_original_rows(monkeypatch):
    monkeypatch.setattr(routes_apologistic, "resolve_active_store", _store)
    captured = {}

    def fake_restore(**kwargs):
        captured.update(kwargs)
        return {
            "changed": 1,
            "rows": [{
                "employee_afm": "123456789", "work_date": "13/08/2026",
                "status": "review", "proposed": "09:58–17:58",
            }],
            "counts": {"review": 1, "change": 0, "ok": 0},
        }

    monkeypatch.setattr(routes_apologistic, "restore_review_change", fake_restore)
    client = _app().test_client()
    response = client.put("/api/apologistic/restore-review", json={
        "week_from": "2026-08-10",
        "employee_afm": "123456789",
        "work_date": "13/08/2026",
    })

    assert response.status_code == 200
    assert response.json["rows"][0]["status"] == "review"
    assert captured["work_date"] == date(2026, 8, 13)


def test_exchange_returns_both_changed_rows(monkeypatch):
    monkeypatch.setattr(routes_apologistic, "resolve_active_store", _store)
    captured = {}

    def fake_apply_exchange(**kwargs):
        captured.update(kwargs)
        return {
            "changed": True,
            "rows": [
                {"employee_afm": "123456789", "work_date": "09/08/2026", "day_state": "Εργασία",
                 "proposed": "17:23–01:23", "status": "change", "change_from_review": True},
                {"employee_afm": "123456789", "work_date": "08/08/2026", "day_state": "Ρεπό",
                 "proposed": "ΑΝΑΠΑΥΣΗ/ΡΕΠΟ", "status": "change", "change_from_review": True},
            ],
        }

    monkeypatch.setattr(routes_apologistic, "apply_exchange", fake_apply_exchange)
    app = _app()
    app.secret_key = "test"
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["office_user"] = "tester"
    response = client.put("/api/apologistic/exchange", json={
        "week_from": "2026-08-03",
        "employee_afm": "123456789",
        "rest_work_date": "09/08/2026",
        "replacement_work_date": "08/08/2026",
    })
    assert response.status_code == 200
    body = response.get_json()
    assert len(body["rows"]) == 2
    assert all(row["status"] == "change" for row in body["rows"])
    assert all(row["change_from_review"] is True for row in body["rows"])
    assert captured["rest_work_date"] == date(2026, 8, 9)
    assert captured["replacement_work_date"] == date(2026, 8, 8)


def test_accept_all_review_returns_changed_count(monkeypatch):
    monkeypatch.setattr(routes_apologistic, "resolve_active_store", _store)
    monkeypatch.setattr(
        routes_apologistic, "accept_all_review",
        lambda **kwargs: {"changed": len(kwargs.get("items") or []), "skipped": 0, "counts": {"review": 0, "change": 2}},
    )
    app = _app()
    app.secret_key = "test"
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["office_user"] = "tester"
    response = client.put("/api/apologistic/accept-all-review", json={
        "week_from": "2026-08-03",
        "items": [
            {"employee_afm": "123456789", "work_date": "04/08/2026"},
            {"employee_afm": "987654321", "work_date": "05/08/2026"},
        ],
    })
    assert response.status_code == 200
    assert response.get_json()["changed"] == 2


def test_accept_uneven_distribution_group_route(monkeypatch):
    monkeypatch.setattr(routes_apologistic, "resolve_active_store", _store)
    captured = {}
    monkeypatch.setattr(
        routes_apologistic, "accept_uneven_distribution_group",
        lambda **kwargs: captured.update(kwargs) or {
            "changed": 3, "group_id": kwargs["group_id"], "days": [],
            "counts": {"review": 0, "change": 3},
        },
    )
    app = _app()
    app.secret_key = "test"
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["office_user"] = "tester"
    response = client.put("/api/apologistic/uneven-distribution/accept", json={
        "week_from": "2026-08-03", "employee_afm": "123456789",
        "group_id": "UD-1234567890abcdef",
    })
    assert response.status_code == 200
    assert response.get_json()["changed"] == 3
    assert captured["store_id"] == 12
    assert captured["week_from"] == date(2026, 8, 3)
    assert captured["changed_by"] == "tester"


def test_export_returns_xlsx(monkeypatch):
    monkeypatch.setattr(routes_apologistic, "resolve_active_store", _store)
    monkeypatch.setattr(routes_apologistic, "tables_available", lambda: True)
    app = _app()
    client = app.test_client()
    response = client.post("/api/apologistic/export", json={
        "week_from": "2026-06-29",
        "store_name": "ΥΑΔΕΣ",
        "period_label": "29/06–05/07 · 30 αποτελέσματα",
        "filter_label": "φίλτρο: Για έλεγχο",
        "headers": ["Ημέρα", "Εργαζόμενος", "Πρόταση"],
        "rows": [["01/07/2026", "ΑΘΑΝΑΣΙΟΥ ΓΕΩΡΓΙΟΣ", "17:55–00:57"]],
    })
    assert response.status_code == 200
    assert response.headers["Content-Type"].startswith(
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert response.data[:2] == b"PK"


def test_proposal_update_returns_persisted_history(monkeypatch):
    monkeypatch.setattr(routes_apologistic, "resolve_active_store", _store)
    monkeypatch.setattr(routes_apologistic, "update_proposed", lambda **kwargs: {"proposed": kwargs["proposed"], "changed": True})
    monkeypatch.setattr(
        routes_apologistic, "load_report",
        lambda *_: ({"days": [{"employee_afm": "123456789", "work_date": "04/08/2026",
                                "proposal_history": [{"old_value": "08:00–16:00", "new_value": "09:00–17:00"}]}]}, {}),
    )
    app = _app()
    app.secret_key = "test"
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["office_user"] = "tester"
    response = client.put("/api/apologistic/proposal", json={
        "week_from": "2026-08-03", "work_date": "04/08/2026",
        "employee_afm": "123456789", "proposed": "09:00–17:00",
    })
    assert response.status_code == 200
    assert response.get_json()["history"][0]["new_value"] == "09:00–17:00"
