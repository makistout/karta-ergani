"""API διαχείρισης χρηστών γραφείου."""

from __future__ import annotations

import json
import logging

from flask import Blueprint, jsonify, request

from app.access_control import ROLE_PERMISSIONS, all_permission_codes, current_user_id
from app import repo_store
from app import repo_users
from app.audit_log import list_user_activity, record_audit_event
from app.email_notify import EmailNotConfigured
from app.store_credentials_util import mask_store_secrets
from app.user_email_verification import send_verification_email

users_bp = Blueprint("users", __name__, url_prefix="/api/users")
logger = logging.getLogger(__name__)


def _require_tables():
    if not repo_users.tables_available():
        return jsonify({
            "error": "Δεν έχουν δημιουργηθεί οι πίνακες χρηστών",
            "db_setup": "PYTHONPYCACHEPREFIX=/private/tmp/karta-pycache .venv/bin/python scripts/run_migration_office_users.py",
        }), 503
    return None


def _parse_store_ids(data: dict) -> list[int]:
    raw = data.get("store_ids") or []
    if not isinstance(raw, list):
        return []
    out: list[int] = []
    for item in raw:
        try:
            out.append(int(item))
        except (TypeError, ValueError):
            continue
    return out


def _parse_permissions(data: dict) -> list[str]:
    raw = data.get("permissions") or []
    if not isinstance(raw, list):
        return []
    allowed = set(all_permission_codes())
    return sorted({str(x).strip() for x in raw if str(x).strip() in allowed})


def _store_scope_error(data: dict):
    role = str(data.get("role") or "viewer").strip().lower()
    if role == "super_admin":
        return None
    if _parse_store_ids(data):
        return None
    return jsonify({"error": "Επιλέξτε τουλάχιστον ένα κατάστημα για τον χρήστη"}), 400


def _json_user(user: dict) -> dict:
    out = {}
    for key, value in user.items():
        out[key] = value.isoformat() if hasattr(value, "isoformat") else value
    return out


def _json_activity_rows(rows: list) -> list:
    out = []
    for raw in rows:
        row = {}
        for key, value in raw.items():
            if key == "details_json" and isinstance(value, str):
                try:
                    row["details"] = json.loads(value)
                except json.JSONDecodeError:
                    row[key] = value
                continue
            row[key] = value.isoformat() if hasattr(value, "isoformat") else value
        out.append(row)
    return out


def _send_user_verification_email(
    user_id: int,
    user: dict,
    *,
    temporary_password: str | None = None,
) -> str | None:
    email = str(user.get("email") or "").strip()
    if not email:
        return "Ο χρήστης δεν έχει email."
    token = repo_users.create_email_verification_token(user_id)
    if not token:
        return "Δεν έχουν εφαρμοστεί τα πεδία email verification στη βάση."
    send_verification_email(
        email=email,
        username=str(user.get("username") or ""),
        full_name=str(user.get("full_name") or "") or None,
        token=token,
        temporary_password=temporary_password,
    )
    logger.info(
        "Verification email sent user_id=%s username=%s to=%s include_temp_password=%s",
        user_id,
        user.get("username"),
        email,
        bool(temporary_password),
    )
    return None


@users_bp.get("")
def list_users():
    unavailable = _require_tables()
    if unavailable:
        return unavailable
    users = []
    for row in repo_users.list_users():
        user = _json_user(row)
        detail = repo_users.get_user(int(user["id"])) or {}
        user["permissions"] = detail.get("permissions") or []
        user["store_ids"] = detail.get("store_ids") or []
        users.append(user)
    employee_counts = repo_store.list_store_employee_counts()
    stores = []
    for row in repo_store.list_store_configs():
        store = mask_store_secrets(row)
        store["employee_count"] = employee_counts.get(int(store.get("id") or 0), 0)
        stores.append(store)
    return jsonify({
        "users": users,
        "roles": sorted(ROLE_PERMISSIONS.keys()),
        "role_permissions": {
            role: sorted(permissions)
            for role, permissions in ROLE_PERMISSIONS.items()
        },
        "permissions": all_permission_codes(),
        "stores": stores,
    })


@users_bp.get("/<int:user_id>")
def get_user(user_id: int):
    unavailable = _require_tables()
    if unavailable:
        return unavailable
    user = repo_users.get_user(user_id)
    if not user:
        return jsonify({"error": "Δεν βρέθηκε χρήστης"}), 404
    return jsonify(_json_user(user))


@users_bp.get("/<int:user_id>/activity")
def user_activity(user_id: int):
    unavailable = _require_tables()
    if unavailable:
        return unavailable
    user = repo_users.get_user(user_id)
    if not user:
        return jsonify({"error": "Δεν βρέθηκε χρήστης"}), 404
    try:
        limit = int(request.args.get("limit") or 50)
    except (TypeError, ValueError):
        limit = 50
    before_raw = request.args.get("before_id")
    before_id = None
    if before_raw not in (None, ""):
        try:
            before_id = int(before_raw)
        except (TypeError, ValueError):
            return jsonify({"error": "Μη έγκυρο before_id"}), 400
    result = list_user_activity(
        str(user.get("username") or ""),
        limit=limit,
        before_id=before_id,
    )
    return jsonify({
        "success": True,
        "user": {
            "id": user.get("id"),
            "username": user.get("username"),
            "email": user.get("email"),
            "full_name": user.get("full_name"),
            "terms_accepted_at": (
                user.get("terms_accepted_at").isoformat()
                if hasattr(user.get("terms_accepted_at"), "isoformat")
                else user.get("terms_accepted_at")
            ),
            "terms_accepted_ip": user.get("terms_accepted_ip"),
            "terms_version": user.get("terms_version"),
        },
        "rows": _json_activity_rows(result.get("rows") or []),
        "has_more": bool(result.get("has_more")),
        "limit": result.get("limit"),
        "next_before_id": result.get("next_before_id"),
    })


@users_bp.delete("/<int:user_id>")
def delete_user(user_id: int):
    unavailable = _require_tables()
    if unavailable:
        return unavailable
    user = repo_users.get_user(user_id)
    if not user:
        return jsonify({"error": "Δεν βρέθηκε χρήστης"}), 404
    me = current_user_id()
    if me is not None and int(me) == int(user_id):
        return jsonify({"error": "Δεν μπορείτε να διαγράψετε τον δικό σας λογαριασμό"}), 400
    if repo_users.is_super_admin_user(user) and repo_users.count_super_admin_users() <= 1:
        return jsonify({"error": "Δεν μπορείτε να διαγράψετε τον τελευταίο super_admin"}), 400
    username = str(user.get("username") or "")
    if not repo_users.delete_user(user_id):
        return jsonify({"error": "Αποτυχία διαγραφής χρήστη"}), 400
    record_audit_event(
        action="users.deleted",
        success=True,
        http_status=200,
        entity_type="office_user",
        entity_id=username or str(user_id),
        details={
            "deleted_user_id": int(user_id),
            "username": username,
            "email": user.get("email"),
            "role": user.get("role"),
        },
    )
    return jsonify({"success": True, "id": int(user_id), "username": username})


@users_bp.post("")
def create_user():
    unavailable = _require_tables()
    if unavailable:
        return unavailable
    data = request.get_json(silent=True) or {}
    username = str(data.get("username") or "").strip()
    password = str(data.get("password") or "")
    email = str(data.get("email") or "").strip()
    if not username or not password:
        return jsonify({"error": "Συμπληρώστε username και password"}), 400
    if not email or "@" not in email:
        return jsonify({"error": "Συμπληρώστε έγκυρο email για επιβεβαίωση λογαριασμού"}), 400
    store_scope_error = _store_scope_error(data)
    if store_scope_error:
        return store_scope_error
    try:
        user_id = repo_users.create_user(
            username=username,
            password=password,
            email=email,
            full_name=str(data.get("full_name") or "").strip() or None,
            role=str(data.get("role") or "viewer"),
            is_active=bool(data.get("is_active", True)),
            permissions=_parse_permissions(data),
            store_ids=_parse_store_ids(data),
            must_change_password=True,
        )
    except Exception as ex:
        return jsonify({"error": f"Αποτυχία δημιουργίας χρήστη: {ex}"}), 400
    user = repo_users.get_user(int(user_id))
    email_warning = None
    if user:
        try:
            email_warning = _send_user_verification_email(
                int(user_id),
                user,
                temporary_password=password,
            )
        except EmailNotConfigured as ex:
            email_warning = str(ex)
        except Exception as ex:
            email_warning = f"Αποτυχία αποστολής email επιβεβαίωσης: {ex}"
    payload = {"success": True, "id": user_id, "user": _json_user(user or {})}
    if email_warning:
        payload["email_warning"] = email_warning
    return jsonify(payload)


@users_bp.get("/verify-email")
def verify_email():
    token = str(request.args.get("t") or request.args.get("token") or "").strip()
    if not token:
        return jsonify({"success": False, "error": "Λείπει token επιβεβαίωσης"}), 400
    user = repo_users.verify_email_token(token)
    if not user:
        return jsonify({"success": False, "error": "Μη έγκυρος ή ληγμένος σύνδεσμος"}), 400
    return jsonify({
        "success": True,
        "message": "Το email επιβεβαιώθηκε.",
        "user": _json_user(user),
    })


@users_bp.put("/<int:user_id>")
def update_user(user_id: int):
    unavailable = _require_tables()
    if unavailable:
        return unavailable
    data = request.get_json(silent=True) or {}
    if not repo_users.get_user(user_id):
        return jsonify({"error": "Δεν βρέθηκε χρήστης"}), 404
    store_scope_error = _store_scope_error(data)
    if store_scope_error:
        return store_scope_error
    repo_users.update_user(
        user_id,
        email=str(data.get("email") or "").strip() or None,
        full_name=str(data.get("full_name") or "").strip() or None,
        role=str(data.get("role") or "viewer"),
        is_active=bool(data.get("is_active", True)),
    )
    if "permissions" in data:
        repo_users.replace_user_permissions(user_id, _parse_permissions(data))
    if "store_ids" in data:
        repo_users.replace_user_stores(user_id, _parse_store_ids(data))
    user = repo_users.get_user(user_id)
    return jsonify({"success": True, "user": _json_user(user or {})})


@users_bp.post("/<int:user_id>/resend-verification-email")
def resend_verification_email(user_id: int):
    unavailable = _require_tables()
    if unavailable:
        return unavailable
    user = repo_users.get_user(user_id)
    if not user:
        return jsonify({"error": "Δεν βρέθηκε χρήστης"}), 404
    from app.user_email_verification import new_temporary_password

    temporary_password = new_temporary_password()
    repo_users.reset_password(user_id, temporary_password, must_change_password=True)
    try:
        email_warning = _send_user_verification_email(
            user_id,
            user,
            temporary_password=temporary_password,
        )
    except EmailNotConfigured as ex:
        return jsonify({"error": str(ex)}), 503
    except Exception as ex:
        return jsonify({"error": f"Αποτυχία αποστολής email επιβεβαίωσης: {ex}"}), 502
    if email_warning:
        return jsonify({"error": email_warning}), 400
    return jsonify({
        "success": True,
        "message": "Στάλθηκε email επιβεβαίωσης με νέο προσωρινό κωδικό.",
    })


@users_bp.post("/<int:user_id>/password")
def reset_password(user_id: int):
    unavailable = _require_tables()
    if unavailable:
        return unavailable
    data = request.get_json(silent=True) or {}
    password = str(data.get("password") or "")
    if not password:
        return jsonify({"error": "Συμπληρώστε νέο password"}), 400
    if not repo_users.get_user(user_id):
        return jsonify({"error": "Δεν βρέθηκε χρήστης"}), 404
    repo_users.reset_password(user_id, password)
    return jsonify({"success": True})


@users_bp.put("/<int:user_id>/permissions")
def update_permissions(user_id: int):
    unavailable = _require_tables()
    if unavailable:
        return unavailable
    if not repo_users.get_user(user_id):
        return jsonify({"error": "Δεν βρέθηκε χρήστης"}), 404
    repo_users.replace_user_permissions(user_id, _parse_permissions(request.get_json(silent=True) or {}))
    return jsonify({"success": True})


@users_bp.put("/<int:user_id>/stores")
def update_stores(user_id: int):
    unavailable = _require_tables()
    if unavailable:
        return unavailable
    if not repo_users.get_user(user_id):
        return jsonify({"error": "Δεν βρέθηκε χρήστης"}), 404
    repo_users.replace_user_stores(user_id, _parse_store_ids(request.get_json(silent=True) or {}))
    return jsonify({"success": True})
