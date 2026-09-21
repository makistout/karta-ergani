from datetime import datetime, timedelta

import pytest
from flask import Flask, jsonify

import app.routes_mobile as mobile
from app.office_auth import register_login_guard
from app.access_control import SESSION_ROLE, permission_for_path


@pytest.fixture
def client(monkeypatch):
    app = Flask(__name__, template_folder="../app/templates")
    app.secret_key = "mobile-test"
    app.url_map.strict_slashes = False
    register_login_guard(app)
    app.register_blueprint(mobile.mobile_bp)
    monkeypatch.setattr("config.Config.OFFICE_API_TOKEN", "")
    return app.test_client()


def login(client, role="admin"):
    with client.session_transaction() as session:
        session["office_logged_in"] = True
        session[SESSION_ROLE] = role


def test_requires_login_and_returns_to_mobile(client):
    response = client.get("/mobile")
    assert response.status_code == 302
    assert response.location == "/ui/login?next=/mobile"
    assert client.get("/api/mobile/roster").status_code == 401
    assert client.post("/api/mobile/submit", json={}).status_code == 401


def test_page_and_permissions(client):
    login(client)
    response = client.get("/mobile")
    assert response.status_code == 200
    assert response.headers["Cache-Control"] == "no-store"
    assert b"css/mobile.css" in response.data
    assert permission_for_path("/mobile/", "GET") == "work_card.view"
    assert permission_for_path("/api/mobile/submit", "POST") == "work_card.submit_live"


def test_viewer_cannot_submit(client):
    login(client, "viewer")
    assert client.post("/api/mobile/submit", json={}).status_code == 403


def test_roster_excludes_days_off_and_combines_split_shifts(monkeypatch):
    rows = [
        {"employee_afm": "123456789", "eponymo": "Δοκιμή", "onoma": "Α", "hour_from": "09:00", "hour_to": "13:00"},
        {"employee_afm": "123456789", "hour_from": "17:00", "hour_to": "21:00"},
        {"employee_afm": "987654321", "shift_type": "ΡΕΠΟ"},
    ]
    monkeypatch.setattr(mobile, "list_schedule_for_store", lambda *a: rows)
    monkeypatch.setattr(mobile, "list_current_for_store", lambda *a, **kw: [
        {"employee_afm": "123456789", "specialty": "Κουζίνα"}])
    result = mobile.today_roster({"employer_afm": "1", "branch_aa": "0"}, datetime(2026, 9, 17).date())
    assert len(result) == 1
    assert result[0]["specialty"] == "Κουζίνα"
    assert result[0]["shifts"] == ["09:00 – 13:00", "17:00 – 21:00"]


@pytest.mark.parametrize("minutes", [0, 5, 10])
def test_submit_uses_server_time_and_existing_pipeline(client, monkeypatch, minutes):
    login(client)
    now = datetime(2026, 9, 17, 0, 3, tzinfo=mobile.tz_athens())
    class Clock:
        @staticmethod
        def now(tz):
            return now
    monkeypatch.setattr(mobile, "datetime", Clock)
    monkeypatch.setattr(mobile, "resolve_active_store", lambda: {"id": 7})
    monkeypatch.setattr(mobile, "today_roster", lambda *a: [{"afm": "123456789"}])
    captured = {}
    def pipeline(body):
        captured.update(body)
        return jsonify(success=True)
    monkeypatch.setattr("app.routes_work_card.work_card_submit_office", pipeline)
    response = client.post("/api/mobile/submit", json={
        "store_id": 7, "date": "2026-09-17", "employee_afm": "123456789",
        "event": "check_out", "minutes": minutes, "correction_mode": True,
    })
    assert response.status_code == 200
    expected = now - timedelta(minutes=minutes)
    assert captured["event_at"] == expected.isoformat(timespec="seconds")
    assert captured["reference_date"] == expected.date().isoformat()
    assert "correction_mode" not in captured


@pytest.mark.parametrize("override, status", [
    ({"store_id": 8}, 409), ({"date": "2000-01-01"}, 409),
    ({"minutes": 6}, 400), ({"minutes": True}, 400),
    ({"event": "invalid"}, 400), ({"employee_afm": "987654321"}, 400),
])
def test_rejects_stale_or_invalid_commands(client, monkeypatch, override, status):
    login(client)
    monkeypatch.setattr(mobile, "resolve_active_store", lambda: {"id": 7})
    monkeypatch.setattr(mobile, "today_roster", lambda *a: [{"afm": "123456789"}])
    body = {"store_id": 7, "date": datetime.now(mobile.tz_athens()).date().isoformat(),
            "employee_afm": "123456789", "event": "check_in", "minutes": 0}
    assert client.post("/api/mobile/submit", json={**body, **override}).status_code == status

def test_punches_and_completed_split_shifts(monkeypatch):
    import app.repo_work_log as logs
    rows = [
        {'employee_afm': '123456789', 'hour_from': '09:01', 'hour_to': '17:03'},
        {'employee_afm': '234567890', 'hour_from': '09:00', 'hour_to': ''},
        {'employee_afm': '345678901', 'hour_from': '09:00', 'hour_to': '13:00'},
    ]
    monkeypatch.setattr(logs, 'list_work_log_for_store', lambda *a: rows)
    monkeypatch.setattr(logs, 'normalize_overnight_work_log_rows', lambda rows, **kw: rows)
    monkeypatch.setattr(logs, 'append_card_punches_missing_from_work_log', lambda *a: None)
    monkeypatch.setattr(logs, 'enrich_work_log_rows_with_card_punch', lambda *a: None)
    people = [{'afm': afm, 'shifts': shifts} for afm, shifts in [
        ('123456789', ['09:00 – 17:00']), ('234567890', ['09:00 – 17:00']),
        ('345678901', ['09:00 – 13:00', '17:00 – 21:00']), ('456789012', ['09:00 – 17:00'])]]
    mobile.attach_punches(people, {'employer_afm': '1', 'branch_aa': '0'}, datetime(2026, 9, 18).date())
    assert [p['completed'] for p in people] == [True, False, False, False]
    assert people[0]['punches'] == [{'in': '09:01', 'out': '17:03'}]
    assert people[3]['punches'] == []
