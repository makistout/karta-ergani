"""Private rule diagrams: office password session AND explicit super-admin role."""
from urllib.parse import quote

from flask import Blueprint, abort, make_response, redirect, render_template, request, send_file, session

from app.access_control import SESSION_ROLE, normalize_role
from app.office_auth import is_office_authenticated
from app.rule_diagram_versions import ARCHIVE, is_current, manifest, version_entry

rule_diagrams_bp = Blueprint('rule_diagrams', __name__, url_prefix='/ui/apologistic/rules')


@rule_diagrams_bp.before_request
def require_super_admin_session():
    # Do not accept the office API token, wildcard permissions or default role.
    if not is_office_authenticated():
        return redirect('/ui/login?next=' + quote(request.path, safe='/'))
    if normalize_role(session.get(SESSION_ROLE) or 'viewer') != 'super_admin':
        abort(403)


@rule_diagrams_bp.after_request
def private_response(response):
    response.headers['Cache-Control'] = 'private, no-store, max-age=0'
    response.headers['Vary'] = 'Cookie'
    response.headers['X-Robots-Tag'] = 'noindex, nofollow, noarchive'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    return response


@rule_diagrams_bp.get('')
def index():
    data = manifest()
    selected = request.args.get('version') or data['current']
    entry = version_entry(selected)
    if entry is None:
        abort(404)
    section = request.args.get('section', 'index.html')
    if section not in {'index.html', 'overview.html', 'catalog.html', 'logic.html', 'notes.html'}:
        abort(404)
    return render_template('ui/rule-diagrams.html', section=section, versions=list(reversed(data['versions'])),
                           selected=entry, current_version=data['current'],
                           up_to_date=is_current(version_entry(data['current'])))


@rule_diagrams_bp.get('/view/<version>/<filename>')
def artifact(version, filename):
    entry = version_entry(version)
    if entry is None or filename not in entry['artifacts']:
        abort(404)
    response = make_response(send_file(ARCHIVE / version / filename, conditional=False,
                                      as_attachment=not filename.endswith('.html')))
    if filename.endswith('.html'):
        response.headers['Content-Security-Policy'] = (
            "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; "
            "img-src 'self' data:; frame-ancestors 'self'; base-uri 'none'; form-action 'none'"
        )
    return response
