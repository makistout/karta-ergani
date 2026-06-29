"""API διαχείρισης χρηστών γραφείου."""

from __future__ import annotations

from flask import Blueprint, jsonify, request

from app.access_control import ROLE_PERMISSIONS, all_permission_codes
from app import repo_store
from app import repo_users
from app.store_credentials_util import mask_store_secrets

users_bp = Blueprint("users", __name__, url_prefix="/api/users")


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


def _json_user(user: dict) -> dict:
    out = {}
    for key, value in user.items():
        out[key] = value.isoformat() if hasattr(value, "isoformat") else value
    return out


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


@users_bp.post("")
def create_user():
    unavailable = _require_tables()
    if unavailable:
        return unavailable
    data = request.get_json(silent=True) or {}
    username = str(data.get("username") or "").strip()
    password = str(data.get("password") or "")
    if not username or not password:
        return jsonify({"error": "Συμπληρώστε username και password"}), 400
    try:
        user_id = repo_users.create_user(
            username=username,
            password=password,
            email=str(data.get("email") or "").strip() or None,
            full_name=str(data.get("full_name") or "").strip() or None,
            role=str(data.get("role") or "viewer"),
            is_active=bool(data.get("is_active", True)),
            permissions=_parse_permissions(data),
            store_ids=_parse_store_ids(data),
        )
    except Exception as ex:
        return jsonify({"error": f"Αποτυχία δημιουργίας χρήστη: {ex}"}), 400
    return jsonify({"success": True, "id": user_id})


@users_bp.put("/<int:user_id>")
def update_user(user_id: int):
    unavailable = _require_tables()
    if unavailable:
        return unavailable
    data = request.get_json(silent=True) or {}
    if not repo_users.get_user(user_id):
        return jsonify({"error": "Δεν βρέθηκε χρήστης"}), 404
    repo_users.update_user(
        user_id,
        email=str(data.get("email") or "").strip() or None,
        full_name=str(data.get("full_name") or "").strip() or None,
        role=str(data.get("role") or "viewer"),
        is_active=bool(data.get("is_active", True)),
    )
    return jsonify({"success": True})


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
