import hashlib
import json
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch

import pytest
from flask import Flask, jsonify

from app.routes_scanner import scanner_bp, database, COOKIE


STORE = dict(id=7, name="Test store", employer_afm="123456789", branch_aa="2", web_username="branch-user", web_password="test-only", ergani_env="production")
EMP = dict(afm="987654321", eponymo="TEST", onoma="EMPLOYEE")
HEADERS = {"X-Scanner-Request": "1"}


def test_connectivity_is_fresh_public_and_does_not_touch_database(setup):
    app,client=setup
    with patch('app.routes_scanner.database',side_effect=AssertionError('must not access DB')):
        response=client.get('/scanner/api/connectivity?nonce=test-nonce')
    assert response.status_code==200
    assert response.json=={'service':'erganios-scanner','nonce':'test-nonce'}
    assert response.headers['Cache-Control']=='no-store'


@pytest.fixture
def setup(tmp_path):
    app = Flask(__name__, template_folder="../app/templates", static_folder="../app/static")
    app.config.update(TESTING=True, SECRET_KEY="test", SCANNER_DB_PATH=str(tmp_path / "scanner.sqlite3"))
    app.register_blueprint(scanner_bp)
    with patch("app.routes_scanner.store_menu_details", return_value={"legal_name":"Official Company SA","branch_description":"Athens","last_card_at":"09/09/2026 11:00"}), patch("app.routes_scanner.get_store_config", return_value=STORE), patch("app.routes_scanner.list_store_configs", return_value=[STORE]), patch("app.routes_scanner.list_active_employees_for_store", return_value=[EMP]), patch("app.routes_scanner.Config.SCANNER_DRY_RUN", False):
        yield app, app.test_client()


def sign_in(app, client, pin=None):
    token="test-scanner-token"
    with app.app_context(), database() as db:
        db.execute("INSERT INTO sessions(id,stores,store_id,expires,pin) VALUES(?,?,?,?,?)", (hashlib.sha256(token.encode()).hexdigest(), json.dumps({"7":"branch-user"}), 7, time.time()+3600, pin))
    client.set_cookie(COOKIE, token, path="/scanner/")


def test_scanner_requires_own_session_and_csrf(setup):
    app, client=setup
    assert client.get('/scanner/api/recent').status_code == 401
    assert client.post('/scanner/api/login', json={}).status_code == 403
    assert client.post('/scanner/api/login', json={}, headers={**HEADERS,"Origin":"https://attacker.invalid"}).status_code == 403
    # Πίσω από IIS το host_url είναι loopback· το Origin του browser είναι το PUBLIC_BASE_URL.
    with patch("app.routes_scanner.Config") as cfg:
        cfg.PUBLIC_BASE_URL = "https://erganios.gr"
        r = client.post(
            "/scanner/api/login",
            json={"username": "x", "password": "y"},
            headers={**HEADERS, "Origin": "https://erganios.gr"},
        )
    assert r.status_code != 403
    assert client.get('/scanner/').status_code == 200


def test_branch_and_pin_isolation(setup):
    app,client=setup;sign_in(app,client)
    assert client.post('/scanner/api/store',json={'store_id':8},headers=HEADERS).status_code==403
    assert client.post('/scanner/api/pin',json={'new_pin':'1234'},headers=HEADERS).status_code==200
    with app.app_context(),database() as db: db.execute('UPDATE sessions SET unlocked=0')
    assert client.get('/scanner/api/recent').status_code==403
    assert client.post('/scanner/api/pin',json={'pin':'0000'},headers=HEADERS).status_code==403
    assert client.post('/scanner/api/pin',json={'pin':'1234'},headers=HEADERS).status_code==200


def test_login_verifies_ergani_identity_without_office_session(setup):
    app,client=setup
    auth=Mock(ok=True);auth.json.return_value={'accessToken':'secret-token'}
    identity=Mock(ok=True)
    with patch('app.routes_scanner.ErganiClient') as cls, patch('app.routes_scanner.parse_employer_afm',return_value='123456789'):
        cls.return_value.authenticate.return_value=auth
        cls.return_value.execute_service.return_value=identity
        response=client.post('/scanner/api/login',json={'username':'branch-user','password':'secret'},headers=HEADERS)
    assert response.status_code==200
    assert 'HttpOnly' in response.headers['Set-Cookie']
    assert 'secret' not in response.get_data(as_text=True)
    with client.session_transaction() as sess: assert not sess.get('office_logged_in')
    assert client.get('/scanner/api/session').json['store_id']==7


def test_submit_idempotency_and_employee_scope(setup):
    app,client=setup;sign_in(app,client)
    body={'store_id':7,'request_id':'0123456789-0123456789-0123456789','qr':EMP['afm'],'event':'in','event_at':datetime.now(timezone.utc).isoformat()}
    auth=Mock(ok=True);auth.json.return_value={'accessToken':'token'}
    with patch('app.routes_scanner.ErganiClient') as cls, patch('app.routes_work_card._submit_work_card') as submit:
        cls.return_value.authenticate.return_value=auth
        submit.side_effect=lambda **kwargs: (jsonify(success=True,persisted=True,protocol='P1'),200)
        first=client.post('/scanner/api/submit',json=body,headers=HEADERS)
        second=client.post('/scanner/api/submit',json=body,headers=HEADERS)
        assert first.status_code==second.status_code==200
        assert submit.call_count==1
        assert submit.call_args.kwargs['aa_s']=='2'
    body['qr']='111111111'
    preview = client.post('/scanner/api/preview',json=body,headers=HEADERS)
    assert preview.status_code==400
    assert preview.json['reason']=='no_match'
    assert 'παραρτήματος' in preview.json['error']


def test_preview_explains_missing_and_ambiguous_afm(setup):
    app, client = setup
    sign_in(app, client)
    missing = client.post(
        '/scanner/api/preview',
        json={'qr': 'NO-DIGITS-HERE', 'event': 'in'},
        headers=HEADERS,
    )
    assert missing.status_code == 400
    assert missing.json['reason'] == 'no_afm'
    assert 'ΑΦΜ' in missing.json['error']

    other = dict(EMP, afm='111222333', eponymo='OTHER', onoma='PERSON')
    with patch('app.routes_scanner.list_active_employees_for_store', return_value=[EMP, other]):
        ambiguous = client.post(
            '/scanner/api/preview',
            json={'qr': f"{EMP['afm']} / {other['afm']}", 'event': 'out'},
            headers=HEADERS,
        )
    assert ambiguous.status_code == 400
    assert ambiguous.json['reason'] == 'ambiguous'
    assert 'περισσότερα από ένα' in ambiguous.json['error']


def test_unknown_submission_never_replayed(setup):
    app,client=setup;sign_in(app,client)
    body={'store_id':7,'request_id':'0123456789-0123456789-0123456789','qr':EMP['afm'],'event':'in','event_at':datetime.now(timezone.utc).isoformat()}
    with patch('app.routes_scanner.ErganiClient',side_effect=RuntimeError('network')) as cls:
        assert client.post('/scanner/api/submit',json=body,headers=HEADERS).status_code==503
        response=client.post('/scanner/api/submit',json=body,headers=HEADERS)
        assert response.status_code==409 and response.json['uncertain']
        assert cls.call_count==1


def test_late_submission_requires_explicit_reason(setup):
    app,client=setup;sign_in(app,client)
    body={'store_id':7,'request_id':'0123456789-0123456789-0123456789','qr':EMP['afm'],'event':'in','event_at':(datetime.now(timezone.utc)-timedelta(minutes=16)).isoformat()}
    with patch('app.routes_scanner.ErganiClient') as cls:
        response=client.post('/scanner/api/submit',json=body,headers=HEADERS)
        assert response.status_code==422 and response.json['late']
        cls.assert_not_called()


def test_store_change_cannot_redirect_queued_punch(setup):
    app,client=setup;sign_in(app,client)
    response=client.post('/scanner/api/submit',json={'store_id':8},headers=HEADERS)
    assert response.status_code==409


def test_existing_portal_user_can_login_without_web_credentials(setup):
    app,client=setup
    cfg=dict(STORE,username='EFKA-test',password='stored')
    with patch('app.routes_scanner.list_store_configs',return_value=[cfg]), patch('app.routes_scanner.get_store_config',return_value=cfg), patch('app.portal_schedule_sync._login_session') as portal:
        response=client.post('/scanner/api/login',json={'username':'EFKA-test','password':'entered'},headers=HEADERS)
        assert response.status_code==200
        assert portal.call_args.args[0]['password']=='entered'
        portal.return_value.close.assert_called_once()
        data=client.get('/scanner/api/session').json
        assert data['store_id']==7
        assert data['stores'][0]['name']=='Official Company SA'
        assert data['stores'][0]['username']=='EFKA-test'
        assert data['stores'][0]['last_card_at']=='09/09/2026 11:00'


def test_multi_branch_login_requires_selection_unless_preferred(setup):
    app, client = setup
    store_a = dict(STORE)
    store_b = dict(STORE, id=8, branch_aa="3", name="Second branch")
    auth = Mock(ok=True)
    auth.json.return_value = {"accessToken": "secret-token"}
    identity = Mock(ok=True)

    def get_cfg(store_id):
        return {7: store_a, 8: store_b}.get(int(store_id or 0))

    with patch("app.routes_scanner.list_store_configs", return_value=[store_a, store_b]), \
         patch("app.routes_scanner.get_store_config", side_effect=get_cfg), \
         patch("app.routes_scanner.ErganiClient") as cls, \
         patch("app.routes_scanner.parse_employer_afm", return_value="123456789"):
        cls.return_value.authenticate.return_value = auth
        cls.return_value.execute_service.return_value = identity
        response = client.post(
            "/scanner/api/login",
            json={"username": "branch-user", "password": "secret"},
            headers=HEADERS,
        )
        assert response.status_code == 200
        assert response.json["store_id"] is None
        assert response.json["store_count"] == 2
        session = client.get("/scanner/api/session").json
        assert session["store_id"] is None
        assert session["needs_store_selection"] is True
        assert {row["id"] for row in session["stores"]} == {7, 8}
        assert client.post("/scanner/api/store", json={"store_id": 8}, headers=HEADERS).status_code == 200
        session = client.get("/scanner/api/session").json
        assert session["store_id"] == 8
        assert session["needs_store_selection"] is False

        client.post("/scanner/api/logout", json={}, headers=HEADERS)
        preferred = client.post(
            "/scanner/api/login",
            json={"username": "branch-user", "password": "secret", "preferred_store_id": 8},
            headers=HEADERS,
        )
        assert preferred.status_code == 200
        assert preferred.json["store_id"] == 8
        assert client.get("/scanner/api/session").json["store_id"] == 8


def test_database_failure_is_json_not_debug_html(setup):
    import pyodbc
    app,client=setup
    with patch('app.routes_scanner.list_store_configs',side_effect=pyodbc.OperationalError('08001','connection failed')):
        response=client.post('/scanner/api/login',json={'username':'user','password':'password'},headers=HEADERS)
    assert response.status_code==503
    assert response.is_json and 'error' in response.json


def test_dedupe_recent_punches_prefers_card_with_protocol():
    from app.repo_scanner import _dedupe_recent_punches

    rows = [
        {"employee_afm": "1", "date": "11/09/2026", "event": "in", "time": "11:01",
         "src": "work", "protocol": None, "src_id": 1},
        {"employee_afm": "1", "date": "11/09/2026", "event": "in", "time": "11:01",
         "src": "card", "protocol": "ΚΕ1", "src_id": 2},
        {"employee_afm": "2", "date": "11/09/2026", "event": "in", "time": "09:03",
         "src": "work", "protocol": None, "src_id": 3},
    ]
    out = _dedupe_recent_punches(rows)
    assert len(out) == 2
    assert out[0]["protocol"] == "ΚΕ1" and out[0]["src"] == "card"
    assert out[1]["employee_afm"] == "2"


def test_recent_punches_pagination_is_store_scoped_without_totals(setup):
    app,client=setup;sign_in(app,client)
    with patch('app.repo_scanner.recent_punches',return_value=([{'id':42,'event':'out'}],True)) as query:
        response=client.get('/scanner/api/recent?page=1')
    assert response.status_code==200
    assert response.json=={'events':[{'id':42,'event':'out'}],'has_next':True,'has_previous':True,'page':1,'limit':20}
    query.assert_called_once_with('123456789','2',1, page_size=20)
    assert client.get('/scanner/api/recent?page=-1').status_code==400


def test_scanner_session_does_not_unlock_office_routes(setup):
    from app.office_auth import register_login_guard
    app,client=setup
    app.add_url_rule('/api/private-office',view_func=lambda: jsonify(success=True))
    with patch('app.office_auth.office_login_enabled',return_value=True):
        register_login_guard(app)
    sign_in(app,client)
    assert client.get('/scanner/api/session').status_code==200
    assert client.get('/api/private-office').status_code==401


def test_dry_run_submit_skips_ergani_and_returns_preview(setup):
    app, client = setup
    sign_in(app, client)
    body = {
        "store_id": 7,
        "request_id": "dry-run-0123456789-0123456789",
        "qr": EMP["afm"],
        "event": "in",
        "event_at": datetime.now(timezone.utc).isoformat(),
    }
    with patch("app.routes_scanner.Config") as cfg, patch("app.routes_scanner.ErganiClient") as cls, patch(
        "app.routes_work_card._submit_work_card"
    ) as submit:
        cfg.SCANNER_DRY_RUN = True
        cfg.PUBLIC_BASE_URL = "https://erganios.gr"
        response = client.post("/scanner/api/submit", json=body, headers=HEADERS)
        assert response.status_code == 200
        data = response.json
        assert data["success"] is True
        assert data["dry_run"] is True
        assert data["persisted"] is False
        assert data["protocol"] is None
        assert "DRY-RUN" in data["preview"]
        assert data["would_send"]["employee_afm"] == EMP["afm"]
        assert data["would_send"]["branch_aa"] == "2"
        assert data["would_send"]["ergani_body"]["Cards"]["Card"][0]["f_aa"] == "2"
        cls.assert_not_called()
        submit.assert_not_called()
    with patch("app.routes_scanner.Config") as cfg:
        cfg.SCANNER_DRY_RUN = True
        session = client.get("/scanner/api/session").json
        assert session["dry_run"] is True


def test_offline_iso_timestamp_and_late_reason_reach_existing_submit(setup):
    app,client=setup;sign_in(app,client)
    body={'store_id':7,'request_id':'0123456789-0123456789-0123456789','qr':EMP['afm'],'event':'in','aitiologia':'003','event_at':(datetime.now(timezone.utc)-timedelta(minutes=16)).isoformat().replace('+00:00','Z')}
    auth=Mock(ok=True);auth.json.return_value={'accessToken':'token'}
    with patch('app.routes_scanner.ErganiClient') as cls, patch('app.routes_work_card._submit_work_card') as submit:
        cls.return_value.authenticate.return_value=auth
        submit.side_effect=lambda **kwargs: (jsonify(success=True,persisted=True),200)
        response=client.post('/scanner/api/submit',json=body,headers=HEADERS)
        assert response.status_code==200
        assert submit.call_args.kwargs['body']['aitiologia']=='003'
        client.post('/scanner/api/submit',json=body,headers=HEADERS)
        assert submit.call_count==1


def test_submit_forwards_correction_offer_and_correction_mode(setup):
    app, client = setup
    sign_in(app, client)
    body = {
        "store_id": 7,
        "request_id": "0123456789-corr-offer-0000001",
        "qr": EMP["afm"],
        "event": "in",
        "event_at": datetime.now(timezone.utc).isoformat(),
    }
    auth = Mock(ok=True)
    auth.json.return_value = {"accessToken": "token"}
    offer = {
        "success": False,
        "correction_available": True,
        "error": "Υπάρχει ήδη ίδιο χτύπημα",
        "existing_event": {"time": "09:00", "protocol": "P-OLD"},
        "attempted_event": {"time": "10:15"},
        "employee_afm": EMP["afm"],
        "employee_name": "TEST EMPLOYEE",
        "reference_date": "2026-09-11",
        "f_type": "0",
    }
    with patch("app.routes_scanner.ErganiClient") as cls, patch(
        "app.routes_work_card._submit_work_card"
    ) as submit:
        cls.return_value.authenticate.return_value = auth
        submit.side_effect = lambda **kwargs: (jsonify(**offer), 409)
        first = client.post("/scanner/api/submit", json=body, headers=HEADERS)
        assert first.status_code == 409
        assert first.json["correction_available"] is True
        assert first.json["existing_event"]["protocol"] == "P-OLD"
        assert submit.call_args.kwargs["client_device"] == "scanner_pwa"
        assert submit.call_args.kwargs["body"].get("correction_mode") is None

    body2 = dict(body)
    body2["request_id"] = "0123456789-corr-mode-0000002"
    body2["correction_mode"] = True
    with patch("app.routes_scanner.ErganiClient") as cls, patch(
        "app.routes_work_card._submit_work_card"
    ) as submit:
        cls.return_value.authenticate.return_value = auth
        submit.side_effect = lambda **kwargs: (
            jsonify(success=True, persisted=True, protocol="P-NEW", correction_mode=True),
            200,
        )
        second = client.post("/scanner/api/submit", json=body2, headers=HEADERS)
        assert second.status_code == 200
        assert second.json["success"] is True
        assert second.json["correction_mode"] is True
        assert submit.call_args.kwargs["body"]["correction_mode"] is True
        assert submit.call_args.kwargs["body"]["source"] == "scanner_pwa"
