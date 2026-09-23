"""Private diagrams must never be accessible via permissions or API token alone."""
from pathlib import Path
from unittest.mock import patch
import ast
import json
import re
import subprocess
import sys
import pytest
from flask import Flask

from app.access_control import (NAV_ITEMS, SESSION_ROLE, SESSION_PERMISSIONS,
                                SESSION_SUPER_ADMIN, nav_item_allowed, register_access_context)
from app.office_auth import (SESSION_LOGGED_IN, SESSION_TERMS_ACCEPTED, register_login_guard)
from app.routes_rule_diagrams import rule_diagrams_bp
from app.rule_diagram_versions import ROOT, ARCHIVE, manifest, fingerprint, is_current
from config import Config


@pytest.fixture
def client():
    app = Flask(__name__, template_folder=str(ROOT / 'app/templates'), static_folder=str(ROOT / 'app/static'))
    app.secret_key = 'tests-only'
    app.config['TESTING'] = True
    register_access_context(app)
    register_login_guard(app)
    app.register_blueprint(rule_diagrams_bp)
    return app.test_client()


def login(client, role, **extras):
    with client.session_transaction() as session:
        session[SESSION_LOGGED_IN] = True
        session[SESSION_TERMS_ACCEPTED] = True
        if role is not None:
            session[SESSION_ROLE] = role
        session.update(extras)


def paths():
    current = manifest()['current']
    return ['/ui/apologistic/rules'] + [
        f'/ui/apologistic/rules/view/{current}/{name}'
        for name in manifest()['versions'][-1]['artifacts']
    ]


def test_anonymous_redirects_every_artifact_to_password_login(client):
    for path in paths():
        response = client.get(path)
        assert response.status_code == 302
        assert '/ui/login' in response.location
        assert 'no-store' in response.headers['Cache-Control']


@pytest.mark.parametrize('role', ['admin', 'backoffice_admin', 'accountant', 'office', 'office_manager', 'viewer', 'store_viewer', 'notifications_manager', None, 'unknown'])
def test_other_roles_cannot_read_any_private_artifact_even_with_wildcards(client, role):
    login(client, role, **{SESSION_PERMISSIONS: ['*'], SESSION_SUPER_ADMIN: True})
    for path in paths():
        response = client.get(path)
        assert response.status_code == 403, (role, path, response.status_code)
        assert 'no-store' in response.headers['Cache-Control']


def test_api_token_is_not_a_password_session(client):
    with patch.object(Config, 'OFFICE_API_TOKEN', 'test-token'):
        for path in paths():
            response = client.get(path, headers={'X-Office-Token': 'test-token'})
            assert response.status_code == 302
            assert '/ui/login' in response.location


def test_super_admin_has_all_sections_and_downloads(client):
    login(client, 'super_admin')
    for path in paths():
        response = client.get(path)
        assert response.status_code == 200, path
        assert 'no-store' in response.headers['Cache-Control']
        assert 'noindex' in response.headers['X-Robots-Tag']
    for section in ['index.html', 'overview.html', 'catalog.html', 'logic.html', 'notes.html']:
        response = client.get('/ui/apologistic/rules', query_string={'section': section})
        assert response.status_code == 200
        assert section in response.get_data(as_text=True)
    assert manifest()['current'] in client.get('/ui/apologistic/rules').get_data(as_text=True)


def test_sidebar_is_immediately_after_apologistic_and_role_restricted(client):
    index = next(i for i, item in enumerate(NAV_ITEMS) if item['nav'] == 'apologistic')
    item = NAV_ITEMS[index + 1]
    assert item['nav'] == 'rule-diagrams'
    with client.application.test_request_context():
        from flask import session
        session[SESSION_PERMISSIONS] = ['*']
        session[SESSION_SUPER_ADMIN] = True
        for role in ['admin', 'accountant', 'viewer', '']:
            session[SESSION_ROLE] = role
            assert not nav_item_allowed(item)
        session[SESSION_ROLE] = 'super_admin'
        assert nav_item_allowed(item)


def test_unknown_versions_files_and_sections_cannot_escape_archive(client):
    login(client, 'super_admin')
    base = '/ui/apologistic/rules'
    current = manifest()['current']
    for url in [base+'?version=../../.env', base+'?section=../../.env',
                base+f'/view/{current}/manifest.json', base+f'/view/{current}/.env',
                base+'/view/rules-0000000000000000/index.html']:
        assert client.get(url).status_code == 404
    # Flask's only public file tree does not contain the archive or diagrams.
    for url in ['/static/rule_diagrams/index.html', '/static/private/rule_diagrams/manifest.json']:
        assert client.get(url).status_code == 404


def test_changed_sources_are_detected_and_displayed(client):
    entry = manifest()['versions'][-1]
    with patch('app.rule_diagram_versions.fingerprint', return_value=('changed', {})):
        assert not is_current(entry)
        login(client, 'super_admin')
        page = client.get('/ui/apologistic/rules').get_data(as_text=True)
        assert 'χρειάζεται επανέλεγχο' in page


def test_fingerprint_is_cross_platform_and_detects_rule_changes(tmp_path):
    from app.rule_diagram_versions import SOURCE_FILES, DOCUMENT_FILES
    expected, _ = fingerprint()
    for name in SOURCE_FILES + DOCUMENT_FILES:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        data = (ROOT / name).read_bytes()
        if path.suffix != '.docx':
            data = data.replace(b'\r\n', b'\n').replace(b'\n', b'\r\n')
        path.write_bytes(data)
    assert fingerprint(tmp_path)[0] == expected
    with (tmp_path / SOURCE_FILES[0]).open('ab') as changed:
        changed.write(b'\n# changed rule\n')
    assert fingerprint(tmp_path)[0] != expected


def test_archived_rules_cover_all_current_code_identifiers():
    rows = json.loads((ARCHIVE / manifest()['current'] / 'rules.json').read_text(encoding='utf-8'))
    ids = {row['id'] for row in rows}
    assert len(ids) == len(rows)
    for source in ['app/apologistic.py', 'app/apologistic_rules.py']:
        tree = ast.parse((ROOT / source).read_text(encoding='utf-8'))
        identifiers = {node.value for node in ast.walk(tree)
                       if isinstance(node, ast.Constant) and isinstance(node.value, str)
                       and re.fullmatch('[A-Z][A-Z_]{5,}', node.value)}
        assert not identifiers - ids


def test_version_archive_and_current_outputs_are_fresh():
    result = subprocess.run([sys.executable, 'scripts/build_rule_diagrams.py', '--check'],
                            cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_archive_eol_conversion_preserves_integrity_check():
    import runpy
    from hashlib import sha256
    matches = runpy.run_path(str(ROOT / 'scripts/build_rule_diagrams.py'))['artifact_matches']
    lf = b'original\ntext\n'
    crlf = lf.replace(b'\n', b'\r\n')
    assert matches(lf, sha256(crlf).hexdigest(), 'index.html')
    assert matches(crlf, sha256(lf).hexdigest(), 'index.html')
    assert not matches(b'changed\ntext\n', sha256(crlf).hexdigest(), 'index.html')
    assert not matches(lf, sha256(crlf).hexdigest(), 'complete.zip')
