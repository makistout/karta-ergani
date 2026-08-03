"""API σύνδεσης / αποσύνδεσης γραφείου."""

from __future__ import annotations

from flask import Blueprint, jsonify, request, session

from app.access_control import SESSION_ROLE, SESSION_USER_ID, accessible_store_ids, is_admin_role, user_payload
from app.audit_log import record_audit_event
from app.client_request import capture_client_context
from app.office_auth import (
    SESSION_MUST_CHANGE_PASSWORD,
    SESSION_TERMS_ACCEPTED,
    SESSION_USER,
    clear_must_change_password_session,
    is_office_authenticated,
    login_office_user,
    logout_office_user,
    mark_terms_accepted_session,
    office_login_enabled,
    onboarding_redirect_path,
)
from app.user_terms import CURRENT_TERMS_VERSION, terms_payload

auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")


def _auto_select_default_store_for_non_admin() -> None:
    role = str(session.get(SESSION_ROLE) or "").strip()
    if is_admin_role(role):
        return

    allowed = accessible_store_ids()
    if not allowed:
        return

    current_id = session.get("active_store_id")
    try:
        current_id = int(current_id) if current_id is not None else None
    except (TypeError, ValueError):
        current_id = None

    if current_id in allowed:
        return

    from app import repo_store as repo
    from app.ergani_env import store_api_context

    rows = repo.list_store_configs()
    candidate = next((row for row in rows if int(row.get("id") or 0) in allowed), None)
    if not candidate:
        return

    ctx = store_api_context(candidate)
    session["active_store_id"] = int(candidate["id"])
    session["employer_afm"] = ctx["employer_afm"]
    session["branch_aa"] = ctx["branch_aa"]
    session["ergani_env"] = ctx["ergani_env"]
    session.pop("ergani_bearer", None)
    session.pop("ergani_bearer_store_id", None)
    session.pop("ergani_bearer_env", None)


def _onboarding_payload() -> dict:
    redirect = onboarding_redirect_path()
    return {
        "must_change_password": bool(session.get(SESSION_MUST_CHANGE_PASSWORD)),
        "terms_accepted": bool(session.get(SESSION_TERMS_ACCEPTED, True)),
        "onboarding_redirect": redirect,
    }


def _record_auth_event(
    action: str,
    *,
    username: str,
    success: bool,
    http_status: int,
    reason: str | None = None,
    extra: dict | None = None,
) -> None:
    details = {
        "username": username,
        "role": session.get(SESSION_ROLE),
    }
    if reason:
        details["reason"] = reason
    if extra:
        details.update(extra)
    record_audit_event(
        action=action,
        success=success,
        http_status=http_status,
        entity_type="office_user",
        entity_id=username or None,
        details=details,
    )


@auth_bp.get("/status")
def auth_status():
    if not office_login_enabled():
        return jsonify({"login_required": False, "authenticated": True})
    if is_office_authenticated():
        _auto_select_default_store_for_non_admin()
    payload = {
        "login_required": True,
        "authenticated": is_office_authenticated(),
        **(
            user_payload(session.get(SESSION_USER), session.get(SESSION_ROLE))
            if is_office_authenticated()
            else {"user": None, "role": None, "permissions": []}
        ),
    }
    if is_office_authenticated():
        payload.update(_onboarding_payload())
    return jsonify(payload)


@auth_bp.post("/login")
def auth_login():
    if not office_login_enabled():
        return jsonify({"success": True, "login_required": False})
    data = request.get_json(silent=True) or {}
    username = str(data.get("username") or "").strip()
    password = str(data.get("password") or "")
    if not username or not password:
        _record_auth_event(
            "auth.login_failed",
            username=username,
            success=False,
            http_status=400,
            reason="missing_credentials",
        )
        return jsonify({"error": "Συμπληρώστε username και password"}), 400
    if not login_office_user(username, password):
        _record_auth_event(
            "auth.login_failed",
            username=username,
            success=False,
            http_status=401,
            reason="invalid_credentials",
        )
        return jsonify({"error": "Λάθος username ή password"}), 401
    _auto_select_default_store_for_non_admin()
    _record_auth_event(
        "auth.login_success",
        username=str(session.get(SESSION_USER) or username),
        success=True,
        http_status=200,
    )
    return jsonify({
        "success": True,
        **user_payload(session.get(SESSION_USER), session.get(SESSION_ROLE)),
        **_onboarding_payload(),
    })


@auth_bp.post("/logout")
def auth_logout():
    username = str(session.get(SESSION_USER) or "").strip()
    if username:
        _record_auth_event(
            "auth.logout",
            username=username,
            success=True,
            http_status=200,
        )
    logout_office_user()
    return jsonify({"success": True})


@auth_bp.get("/terms")
def auth_terms():
    if not is_office_authenticated():
        return jsonify({"error": "Απαιτείται σύνδεση"}), 401
    return jsonify({"success": True, **terms_payload()})


@auth_bp.post("/change-password")
def auth_change_password():
    if not is_office_authenticated():
        return jsonify({"error": "Απαιτείται σύνδεση"}), 401
    user_id = session.get(SESSION_USER_ID)
    try:
        user_id = int(user_id) if user_id is not None else None
    except (TypeError, ValueError):
        user_id = None
    if not user_id:
        return jsonify({"error": "Η αλλαγή κωδικού δεν υποστηρίζεται για αυτόν τον λογαριασμό"}), 400
    data = request.get_json(silent=True) or {}
    current_password = str(data.get("current_password") or "")
    new_password = str(data.get("new_password") or "")
    confirm = str(data.get("confirm_password") or data.get("new_password_confirm") or "")
    if not current_password or not new_password:
        return jsonify({"error": "Συμπληρώστε τον τρέχοντα και τον νέο κωδικό"}), 400
    if new_password != confirm:
        return jsonify({"error": "Η επιβεβαίωση νέου κωδικού δεν ταιριάζει"}), 400
    from app import repo_users

    err = repo_users.change_own_password(user_id, current_password, new_password)
    if err:
        return jsonify({"error": err}), 400
    clear_must_change_password_session()
    username = str(session.get(SESSION_USER) or "")
    _record_auth_event(
        "auth.password_changed",
        username=username,
        success=True,
        http_status=200,
    )
    return jsonify({
        "success": True,
        "message": "Ο κωδικός άλλαξε.",
        **_onboarding_payload(),
    })


@auth_bp.post("/accept-terms")
def auth_accept_terms():
    if not is_office_authenticated():
        return jsonify({"error": "Απαιτείται σύνδεση"}), 401
    if bool(session.get(SESSION_MUST_CHANGE_PASSWORD)):
        return jsonify({
            "error": "Απαιτείται πρώτα αλλαγή κωδικού",
            "redirect": "/ui/change-password",
        }), 403
    user_id = session.get(SESSION_USER_ID)
    try:
        user_id = int(user_id) if user_id is not None else None
    except (TypeError, ValueError):
        user_id = None
    if not user_id:
        return jsonify({"error": "Η αποδοχή όρων δεν υποστηρίζεται για αυτόν τον λογαριασμό"}), 400
    data = request.get_json(silent=True) or {}
    if not bool(data.get("accepted")):
        return jsonify({"error": "Πρέπει να αποδεχτείτε τους όρους χρήσης"}), 400
    version = str(data.get("terms_version") or CURRENT_TERMS_VERSION).strip() or CURRENT_TERMS_VERSION
    client_ctx = capture_client_context("accept_terms")
    client_ip = client_ctx.get("client_ip")
    from app import repo_users

    repo_users.accept_terms(user_id, client_ip=client_ip, terms_version=version)
    mark_terms_accepted_session()
    username = str(session.get(SESSION_USER) or "")
    _record_auth_event(
        "auth.terms_accepted",
        username=username,
        success=True,
        http_status=200,
        extra={
            "terms_version": version,
            "client_ip": client_ip,
        },
    )
    return jsonify({
        "success": True,
        "message": "Οι όροι αποδεχτήκαν.",
        "terms_version": version,
        "client_ip": client_ip,
        **_onboarding_payload(),
    })


_FORGOT_PASSWORD_OK_MSG = (
    "Αν υπάρχει λογαριασμός με αυτά τα στοιχεία, θα λάβετε email με σύνδεσμο επαναφοράς."
)


@auth_bp.post("/forgot-password")
def auth_forgot_password():
    if not office_login_enabled():
        return jsonify({"error": "Η σύνδεση γραφείου δεν είναι ενεργή"}), 400
    data = request.get_json(silent=True) or {}
    identity = str(data.get("username") or data.get("email") or data.get("identity") or "").strip()
    if not identity:
        return jsonify({"error": "Συμπληρώστε username ή email"}), 400

    from app import repo_users
    from app.email_notify import EmailNotConfigured
    from app.user_password_reset import send_password_reset_email

    if not repo_users.password_reset_available():
        return jsonify({
            "error": "Η επαναφορά κωδικού δεν είναι διαθέσιμη ακόμα. Επικοινωνήστε με διαχειριστή.",
        }), 503

    user = repo_users.find_active_user_for_password_reset(identity)
    # Ίδια απάντηση είτε υπάρχει είτε όχι (anti-enumeration).
    if not user or not str(user.get("email") or "").strip():
        return jsonify({"success": True, "message": _FORGOT_PASSWORD_OK_MSG})

    try:
        token = repo_users.create_password_reset_token(int(user["id"]))
        if not token:
            return jsonify({"success": True, "message": _FORGOT_PASSWORD_OK_MSG})
        send_password_reset_email(
            email=str(user["email"]).strip(),
            username=str(user.get("username") or ""),
            full_name=str(user.get("full_name") or "") or None,
            token=token,
        )
    except EmailNotConfigured:
        return jsonify({
            "error": "Η αποστολή email δεν είναι ρυθμισμένη. Επικοινωνήστε με διαχειριστή.",
        }), 503
    except Exception:
        return jsonify({
            "error": "Αποτυχία αποστολής email επαναφοράς. Δοκιμάστε ξανά αργότερα.",
        }), 502

    _record_auth_event(
        "auth.password_reset_requested",
        username=str(user.get("username") or identity),
        success=True,
        http_status=200,
    )
    return jsonify({"success": True, "message": _FORGOT_PASSWORD_OK_MSG})


@auth_bp.post("/reset-password")
def auth_reset_password():
    if not office_login_enabled():
        return jsonify({"error": "Η σύνδεση γραφείου δεν είναι ενεργή"}), 400
    data = request.get_json(silent=True) or {}
    token = str(data.get("token") or data.get("t") or "").strip()
    new_password = str(data.get("new_password") or data.get("password") or "")
    confirm = str(data.get("confirm_password") or data.get("new_password_confirm") or "")
    if not token:
        return jsonify({"error": "Λείπει ο σύνδεσμος επαναφοράς"}), 400
    if not new_password:
        return jsonify({"error": "Συμπληρώστε νέο κωδικό"}), 400
    if new_password != confirm:
        return jsonify({"error": "Η επιβεβαίωση νέου κωδικού δεν ταιριάζει"}), 400

    from app import repo_users

    err = repo_users.reset_password_with_token(token, new_password)
    if err:
        _record_auth_event(
            "auth.password_reset_failed",
            username="",
            success=False,
            http_status=400,
            reason=err,
        )
        return jsonify({"error": err}), 400

    _record_auth_event(
        "auth.password_reset_completed",
        username="",
        success=True,
        http_status=200,
    )
    return jsonify({
        "success": True,
        "message": "Ο κωδικός άλλαξε. Μπορείτε να συνδεθείτε.",
    })
