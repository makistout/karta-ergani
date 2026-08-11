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
