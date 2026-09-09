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
    with patch("app.routes_scanner.store_menu_details", return_value={"legal_name":"Official Company SA","branch_description":"Athens","last_card_at":"09/09/2026 11:00"}), patch("app.routes_scanner.get_store_config", return_value=STORE), patch("app.routes_scanner.list_store_configs", return_value=[STORE]), patch("app.routes_scanner.list_active_employees_for_store", return_value=[EMP]):
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
    assert client.post('/scanner/api/preview',json=body,headers=HEADERS).status_code==400


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


def test_database_failure_is_json_not_debug_html(setup):
    import pyodbc
    app,client=setup
    with patch('app.routes_scanner.list_store_configs',side_effect=pyodbc.OperationalError('08001','connection failed')):
        response=client.post('/scanner/api/login',json={'username':'user','password':'password'},headers=HEADERS)
    assert response.status_code==503
    assert response.is_json and 'error' in response.json


def test_recent_punches_pagination_is_store_scoped_without_totals(setup):
    app,client=setup;sign_in(app,client)
    with patch('app.repo_scanner.recent_punches',return_value=([{'id':42,'event':'out'}],True)) as query:
        response=client.get('/scanner/api/recent?page=1')
    assert response.status_code==200
    assert response.json=={'events':[{'id':42,'event':'out'}],'has_next':True,'has_previous':True}
    query.assert_called_once_with('123456789','2',1)
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
