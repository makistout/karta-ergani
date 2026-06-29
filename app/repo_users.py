"""Office users, roles, permissions and store access."""

from __future__ import annotations

from typing import Any

from werkzeug.security import check_password_hash, generate_password_hash

from app.access_control import ROLE_PERMISSIONS, all_permission_codes, normalize_role
from app.db import cursor
from app.row_util import row_to_dict, rows_to_dicts

_tables_available: bool | None = None
_PASSWORD_HASH_METHOD = "pbkdf2:sha256"


def tables_available() -> bool:
    global _tables_available
    if _tables_available is not None:
        return _tables_available
    try:
        with cursor(commit=False) as cur:
            cur.execute("SELECT OBJECT_ID(N'dbo.karta_user', N'U')")
            row = cur.fetchone()
            _tables_available = bool(row and row[0])
    except Exception:
        _tables_available = False
    return _tables_available


def reset_table_cache() -> None:
    global _tables_available
    _tables_available = None


def seed_roles_permissions() -> None:
    with cursor() as cur:
        for code, permissions in ROLE_PERMISSIONS.items():
            cur.execute(
                """
                IF NOT EXISTS (SELECT 1 FROM dbo.karta_role WHERE code = ?)
                    INSERT INTO dbo.karta_role (code, name, description)
                    VALUES (?, ?, ?)
                ELSE
                    UPDATE dbo.karta_role
                    SET name = ?, updated_at = SYSDATETIMEOFFSET()
                    WHERE code = ?
                """,
                code,
                code,
                code,
                f"Default role: {code}",
                code,
                code,
            )
        for code in all_permission_codes():
            cur.execute(
                """
                IF NOT EXISTS (SELECT 1 FROM dbo.karta_permission WHERE code = ?)
                    INSERT INTO dbo.karta_permission (code, name, description)
                    VALUES (?, ?, ?)
                ELSE
                    UPDATE dbo.karta_permission
                    SET name = ?, updated_at = SYSDATETIMEOFFSET()
                    WHERE code = ?
                """,
                code,
                code,
                code,
                code,
                code,
                code,
            )
        for role_code, permissions in ROLE_PERMISSIONS.items():
            for permission_code in permissions:
                cur.execute(
                    """
                    IF NOT EXISTS (
                        SELECT 1 FROM dbo.karta_role_permission
                        WHERE role_code = ? AND permission_code = ?
                    )
                        INSERT INTO dbo.karta_role_permission (role_code, permission_code)
                        VALUES (?, ?)
                    """,
                    role_code,
                    permission_code,
                    role_code,
                    permission_code,
                )


def seed_super_admin(username: str, password: str, *, full_name: str | None = None) -> int | None:
    user = (username or "").strip()
    pwd = password or ""
    if not user or not pwd:
        return None
    password_hash = generate_password_hash(pwd, method=_PASSWORD_HASH_METHOD)
    with cursor() as cur:
        cur.execute("SELECT id FROM dbo.karta_user WHERE username = ?", user)
        row = cur.fetchone()
        if row:
            user_id = int(row[0])
            cur.execute(
                """
                UPDATE dbo.karta_user
                SET is_active = 1,
                    is_super_admin = 1,
                    full_name = COALESCE(NULLIF(?, N''), full_name),
                    updated_at = SYSDATETIMEOFFSET()
                WHERE id = ?
                """,
                (full_name or "").strip(),
                user_id,
            )
        else:
            cur.execute(
                """
                INSERT INTO dbo.karta_user (
                    username, password_hash, full_name, is_active, is_super_admin
                )
                OUTPUT INSERTED.id
                VALUES (?, ?, ?, 1, 1)
                """,
                user,
                password_hash,
                (full_name or user).strip(),
            )
            user_id = int(cur.fetchone()[0])
        _set_single_role(cur, user_id, "super_admin")
        return user_id


def _set_single_role(cur: Any, user_id: int, role_code: str) -> None:
    role = normalize_role(role_code)
    cur.execute("DELETE FROM dbo.karta_user_role WHERE user_id = ?", int(user_id))
    cur.execute(
        "INSERT INTO dbo.karta_user_role (user_id, role_code) VALUES (?, ?)",
        int(user_id),
        role,
    )


def _role_for_user(cur: Any, user_id: int, *, is_super_admin: bool) -> str:
    if is_super_admin:
        return "super_admin"
    cur.execute("SELECT TOP (1) role_code FROM dbo.karta_user_role WHERE user_id = ?", int(user_id))
    row = cur.fetchone()
    return normalize_role(str(row[0]) if row else "viewer")


def _permissions_for_user(cur: Any, user_id: int, role_code: str, *, is_super_admin: bool) -> list[str]:
    if is_super_admin:
        return ["*"]
    cur.execute(
        "SELECT permission_code FROM dbo.karta_user_permission WHERE user_id = ? ORDER BY permission_code",
        int(user_id),
    )
    return [str(row[0]) for row in cur.fetchall()]


def authenticate_user(username: str, password: str) -> dict[str, Any] | None:
    if not tables_available():
        return None
    user = (username or "").strip()
    with cursor() as cur:
        cur.execute(
            """
            SELECT id, username, email, password_hash, full_name, is_active, is_super_admin
            FROM dbo.karta_user
            WHERE username = ?
            """,
            user,
        )
        row = cur.fetchone()
        data = row_to_dict(cur, row) if row else None
        if not data or not data.get("is_active"):
            return None
        if not check_password_hash(str(data.get("password_hash") or ""), password or ""):
            return None
        user_id = int(data["id"])
        is_sa = bool(data.get("is_super_admin"))
        role = _role_for_user(cur, user_id, is_super_admin=is_sa)
        permissions = _permissions_for_user(cur, user_id, role, is_super_admin=is_sa)
        cur.execute(
            "UPDATE dbo.karta_user SET last_login_at = SYSDATETIMEOFFSET() WHERE id = ?",
            user_id,
        )
        return {
            "id": user_id,
            "username": data["username"],
            "email": data.get("email"),
            "full_name": data.get("full_name"),
            "role": role,
            "is_super_admin": is_sa,
            "permissions": permissions,
        }


def list_users() -> list[dict[str, Any]]:
    if not tables_available():
        return []
    with cursor(commit=False) as cur:
        cur.execute(
            """
            SELECT u.id, u.username, u.email, u.full_name, u.is_active, u.is_super_admin,
                   CAST(u.created_at AS datetime2) AS created_at,
                   CAST(u.updated_at AS datetime2) AS updated_at,
                   CAST(u.last_login_at AS datetime2) AS last_login_at,
                   COALESCE(ur.role_code, CASE WHEN u.is_super_admin = 1 THEN N'super_admin' ELSE N'viewer' END) AS role
            FROM dbo.karta_user u
            LEFT JOIN dbo.karta_user_role ur ON ur.user_id = u.id
            ORDER BY u.username
            """
        )
        return rows_to_dicts(cur)


def get_user(user_id: int) -> dict[str, Any] | None:
    if not tables_available():
        return None
    with cursor(commit=False) as cur:
        cur.execute(
            """
            SELECT u.id, u.username, u.email, u.full_name, u.is_active, u.is_super_admin,
                   COALESCE(ur.role_code, CASE WHEN u.is_super_admin = 1 THEN N'super_admin' ELSE N'viewer' END) AS role
            FROM dbo.karta_user u
            LEFT JOIN dbo.karta_user_role ur ON ur.user_id = u.id
            WHERE u.id = ?
            """,
            int(user_id),
        )
        row = cur.fetchone()
        data = row_to_dict(cur, row) if row else None
        if not data:
            return None
        data["permissions"] = _permissions_for_user(
            cur,
            int(data["id"]),
            str(data.get("role") or "viewer"),
            is_super_admin=bool(data.get("is_super_admin")),
        )
        data["store_ids"] = list_user_store_ids(int(data["id"]))
        return data


def create_user(
    *,
    username: str,
    password: str,
    email: str | None = None,
    full_name: str | None = None,
    role: str = "viewer",
    is_active: bool = True,
    permissions: list[str] | None = None,
    store_ids: list[int] | None = None,
) -> int:
    role_code = normalize_role(role)
    with cursor() as cur:
        cur.execute(
            """
            INSERT INTO dbo.karta_user (
                username, email, password_hash, full_name, is_active, is_super_admin
            )
            OUTPUT INSERTED.id
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            username.strip(),
            (email or "").strip() or None,
            generate_password_hash(password or "", method=_PASSWORD_HASH_METHOD),
            (full_name or "").strip() or None,
            1 if is_active else 0,
            1 if role_code == "super_admin" else 0,
        )
        user_id = int(cur.fetchone()[0])
        _set_single_role(cur, user_id, role_code)
        _replace_permissions(cur, user_id, permissions)
        _replace_stores(cur, user_id, store_ids)
        return user_id


def update_user(
    user_id: int,
    *,
    email: str | None = None,
    full_name: str | None = None,
    role: str = "viewer",
    is_active: bool = True,
) -> None:
    role_code = normalize_role(role)
    with cursor() as cur:
        cur.execute(
            """
            UPDATE dbo.karta_user
            SET email = ?, full_name = ?, is_active = ?, is_super_admin = ?,
                updated_at = SYSDATETIMEOFFSET()
            WHERE id = ?
            """,
            (email or "").strip() or None,
            (full_name or "").strip() or None,
            1 if is_active else 0,
            1 if role_code == "super_admin" else 0,
            int(user_id),
        )
        _set_single_role(cur, int(user_id), role_code)


def reset_password(user_id: int, password: str) -> None:
    with cursor() as cur:
        cur.execute(
            """
            UPDATE dbo.karta_user
            SET password_hash = ?, updated_at = SYSDATETIMEOFFSET()
            WHERE id = ?
            """,
            generate_password_hash(password or "", method=_PASSWORD_HASH_METHOD),
            int(user_id),
        )


def _replace_permissions(cur: Any, user_id: int, permissions: list[str] | None) -> None:
    cur.execute("DELETE FROM dbo.karta_user_permission WHERE user_id = ?", int(user_id))
    for permission in sorted({str(x).strip() for x in (permissions or []) if str(x).strip()}):
        cur.execute(
            """
            INSERT INTO dbo.karta_user_permission (user_id, permission_code)
            VALUES (?, ?)
            """,
            int(user_id),
            permission,
        )


def replace_user_permissions(user_id: int, permissions: list[str]) -> None:
    with cursor() as cur:
        _replace_permissions(cur, int(user_id), permissions)


def list_user_store_ids(user_id: int) -> list[int]:
    if not tables_available():
        return []
    with cursor(commit=False) as cur:
        cur.execute(
            "SELECT store_id FROM dbo.karta_user_store WHERE user_id = ? ORDER BY store_id",
            int(user_id),
        )
        return [int(row[0]) for row in cur.fetchall()]


def _replace_stores(cur: Any, user_id: int, store_ids: list[int] | None) -> None:
    cur.execute("DELETE FROM dbo.karta_user_store WHERE user_id = ?", int(user_id))
    for store_id in sorted({int(x) for x in (store_ids or [])}):
        cur.execute(
            "INSERT INTO dbo.karta_user_store (user_id, store_id) VALUES (?, ?)",
            int(user_id),
            store_id,
        )


def replace_user_stores(user_id: int, store_ids: list[int]) -> None:
    with cursor() as cur:
        _replace_stores(cur, int(user_id), store_ids)


def user_can_access_store(user_id: int | None, store_id: int, *, is_super_admin: bool = False) -> bool:
    if is_super_admin or not tables_available():
        return True
    if not user_id:
        return False
    with cursor(commit=False) as cur:
        cur.execute(
            """
            SELECT 1
            FROM dbo.karta_user_store
            WHERE user_id = ? AND store_id = ?
            """,
            int(user_id),
            int(store_id),
        )
        return cur.fetchone() is not None


def accessible_store_ids(user_id: int | None, *, is_super_admin: bool = False) -> set[int] | None:
    if is_super_admin or not tables_available():
        return None
    if not user_id:
        return set()
    return set(list_user_store_ids(int(user_id)))
