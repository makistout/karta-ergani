"""Office users, roles, permissions and store access."""

from __future__ import annotations

from typing import Any

from werkzeug.security import check_password_hash, generate_password_hash

from app.access_control import ROLE_PERMISSIONS, all_permission_codes, normalize_role
from app.db import cursor
from app.row_util import row_to_dict, rows_to_dicts
from app.user_email_verification import expiry_utc, new_verification_token, token_hash

_tables_available: bool | None = None
_onboarding_available: bool | None = None
_password_reset_available: bool | None = None
_PASSWORD_HASH_METHOD = "pbkdf2:sha256"


def email_verification_available() -> bool:
    if not tables_available():
        return False
    try:
        with cursor(commit=False) as cur:
            cur.execute("SELECT COL_LENGTH(N'dbo.karta_user', N'email_verification_token_hash')")
            row = cur.fetchone()
            return bool(row and row[0] is not None)
    except Exception:
        return False


def onboarding_available() -> bool:
    """True όταν υπάρχουν οι στήλες onboarding.

    Το False δεν κλειδώνει μόνιμα στο cache: μετά από migration χωρίς recycle
    πρέπει να ξαναελεγχθεί.
    """
    global _onboarding_available
    if _onboarding_available is True:
        return True
    if not tables_available():
        return False
    try:
        with cursor(commit=False) as cur:
            cur.execute("SELECT COL_LENGTH(N'dbo.karta_user', N'must_change_password')")
            row = cur.fetchone()
            ok = bool(row and row[0] is not None)
    except Exception:
        ok = False
    if ok:
        _onboarding_available = True
    return ok


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
    global _tables_available, _onboarding_available, _password_reset_available
    _tables_available = None
    _onboarding_available = None
    _password_reset_available = None


def password_reset_available() -> bool:
    global _password_reset_available
    if _password_reset_available is True:
        return True
    if not tables_available():
        return False
    try:
        with cursor(commit=False) as cur:
            cur.execute("SELECT COL_LENGTH(N'dbo.karta_user', N'password_reset_token_hash')")
            row = cur.fetchone()
            ok = bool(row and row[0] is not None)
    except Exception:
        ok = False
    if ok:
        _password_reset_available = True
    return ok


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


def _onboarding_flags_from_row(data: dict[str, Any] | None) -> dict[str, Any]:
    if not data or not onboarding_available():
        return {
            "must_change_password": False,
            "terms_accepted": True,
            "terms_accepted_at": None,
            "terms_accepted_ip": None,
            "terms_version": None,
        }
    accepted_at = data.get("terms_accepted_at")
    return {
        "must_change_password": bool(data.get("must_change_password")),
        "terms_accepted": accepted_at is not None,
        "terms_accepted_at": accepted_at,
        "terms_accepted_ip": data.get("terms_accepted_ip"),
        "terms_version": data.get("terms_version"),
    }


def authenticate_user(username: str, password: str) -> dict[str, Any] | None:
    if not tables_available():
        return None
    user = (username or "").strip()
    onboard = onboarding_available()
    select_cols = (
        "id, username, email, password_hash, full_name, is_active, is_super_admin"
    )
    if onboard:
        select_cols += (
            ", must_change_password, "
            "CAST(terms_accepted_at AS datetime2) AS terms_accepted_at, "
            "terms_accepted_ip, terms_version"
        )
    with cursor() as cur:
        cur.execute(
            f"""
            SELECT {select_cols}
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
            "SELECT store_id FROM dbo.karta_user_store WHERE user_id = ? ORDER BY store_id",
            user_id,
        )
        store_ids = [int(row[0]) for row in cur.fetchall()]
        cur.execute(
            "UPDATE dbo.karta_user SET last_login_at = SYSDATETIMEOFFSET() WHERE id = ?",
            user_id,
        )
        result = {
            "id": user_id,
            "username": data["username"],
            "email": data.get("email"),
            "full_name": data.get("full_name"),
            "role": role,
            "is_super_admin": is_sa,
            "permissions": permissions,
            "store_ids": store_ids,
        }
        result.update(_onboarding_flags_from_row(data))
        return result


def get_user_onboarding(user_id: int) -> dict[str, Any] | None:
    if not onboarding_available():
        return {
            "must_change_password": False,
            "terms_accepted": True,
            "terms_accepted_at": None,
            "terms_accepted_ip": None,
            "terms_version": None,
        }
    with cursor(commit=False) as cur:
        cur.execute(
            """
            SELECT must_change_password,
                   CAST(terms_accepted_at AS datetime2) AS terms_accepted_at,
                   terms_accepted_ip, terms_version
            FROM dbo.karta_user
            WHERE id = ?
            """,
            int(user_id),
        )
        row = cur.fetchone()
        data = row_to_dict(cur, row) if row else None
        if not data:
            return None
        return _onboarding_flags_from_row(data)


def change_own_password(user_id: int, current_password: str, new_password: str) -> str | None:
    """Αλλαγή κωδικού από τον ίδιο τον χρήστη. Επιστρέφει error ή None."""
    new_pwd = str(new_password or "")
    if len(new_pwd) < 8:
        return "Ο νέος κωδικός πρέπει να έχει τουλάχιστον 8 χαρακτήρες."
    with cursor() as cur:
        cur.execute(
            "SELECT password_hash FROM dbo.karta_user WHERE id = ? AND is_active = 1",
            int(user_id),
        )
        row = cur.fetchone()
        if not row:
            return "Δεν βρέθηκε χρήστης."
        if not check_password_hash(str(row[0] or ""), current_password or ""):
            return "Λάθος τρέχων κωδικός."
        if onboarding_available():
            cur.execute(
                """
                UPDATE dbo.karta_user
                SET password_hash = ?,
                    must_change_password = 0,
                    updated_at = SYSDATETIMEOFFSET()
                WHERE id = ?
                """,
                generate_password_hash(new_pwd, method=_PASSWORD_HASH_METHOD),
                int(user_id),
            )
        else:
            cur.execute(
                """
                UPDATE dbo.karta_user
                SET password_hash = ?, updated_at = SYSDATETIMEOFFSET()
                WHERE id = ?
                """,
                generate_password_hash(new_pwd, method=_PASSWORD_HASH_METHOD),
                int(user_id),
            )
    return None


def accept_terms(user_id: int, *, client_ip: str | None, terms_version: str) -> None:
    if not onboarding_available():
        return
    ip = (client_ip or "").strip()[:64] or None
    version = (terms_version or "").strip()[:32] or None
    with cursor() as cur:
        cur.execute(
            """
            UPDATE dbo.karta_user
            SET terms_accepted_at = SYSDATETIMEOFFSET(),
                terms_accepted_ip = ?,
                terms_version = ?,
                updated_at = SYSDATETIMEOFFSET()
            WHERE id = ?
            """,
            ip,
            version,
            int(user_id),
        )


def find_active_user_for_password_reset(username_or_email: str) -> dict[str, Any] | None:
    """Εύρεση ενεργού χρήστη με username ή email (για forgot password)."""
    if not tables_available():
        return None
    raw = (username_or_email or "").strip()
    if not raw:
        return None
    with cursor(commit=False) as cur:
        cur.execute(
            """
            SELECT TOP (1) id, username, email, full_name, is_active
            FROM dbo.karta_user
            WHERE is_active = 1
              AND (
                    username = ?
                 OR (email IS NOT NULL AND LOWER(email) = LOWER(?))
              )
            ORDER BY CASE WHEN username = ? THEN 0 ELSE 1 END, id
            """,
            raw,
            raw,
            raw,
        )
        row = cur.fetchone()
        return row_to_dict(cur, row) if row else None


def create_password_reset_token(user_id: int) -> str | None:
    if not password_reset_available():
        return None
    from app.user_password_reset import new_reset_token, reset_expiry_utc

    token, hashed = new_reset_token()
    with cursor() as cur:
        cur.execute(
            """
            UPDATE dbo.karta_user
            SET password_reset_token_hash = ?,
                password_reset_sent_at = SYSDATETIMEOFFSET(),
                password_reset_expires_at = ?,
                updated_at = SYSDATETIMEOFFSET()
            WHERE id = ? AND is_active = 1 AND email IS NOT NULL
            """,
            hashed,
            reset_expiry_utc(),
            int(user_id),
        )
        if cur.rowcount == 0:
            return None
    return token


def reset_password_with_token(token: str, new_password: str) -> str | None:
    """Ορισμός νέου κωδικού μέσω token. Επιστρέφει error ή None."""
    if not password_reset_available():
        return "Η επαναφορά κωδικού δεν είναι διαθέσιμη."
    new_pwd = str(new_password or "")
    if len(new_pwd) < 8:
        return "Ο νέος κωδικός πρέπει να έχει τουλάχιστον 8 χαρακτήρες."
    from app.user_password_reset import token_hash as reset_token_hash

    hashed = reset_token_hash(token)
    with cursor() as cur:
        cur.execute(
            """
            SELECT TOP (1) id
            FROM dbo.karta_user
            WHERE password_reset_token_hash = ?
              AND password_reset_expires_at >= SYSDATETIMEOFFSET()
              AND is_active = 1
            """,
            hashed,
        )
        row = cur.fetchone()
        if not row:
            return "Μη έγκυρος ή ληγμένος σύνδεσμος επαναφοράς."
        user_id = int(row[0])
        if onboarding_available():
            cur.execute(
                """
                UPDATE dbo.karta_user
                SET password_hash = ?,
                    must_change_password = 0,
                    password_reset_token_hash = NULL,
                    password_reset_expires_at = NULL,
                    updated_at = SYSDATETIMEOFFSET()
                WHERE id = ?
                """,
                generate_password_hash(new_pwd, method=_PASSWORD_HASH_METHOD),
                user_id,
            )
        else:
            cur.execute(
                """
                UPDATE dbo.karta_user
                SET password_hash = ?,
                    password_reset_token_hash = NULL,
                    password_reset_expires_at = NULL,
                    updated_at = SYSDATETIMEOFFSET()
                WHERE id = ?
                """,
                generate_password_hash(new_pwd, method=_PASSWORD_HASH_METHOD),
                user_id,
            )
    return None


def list_users() -> list[dict[str, Any]]:
    if not tables_available():
        return []
    onboard = onboarding_available()
    extra = ""
    if onboard:
        extra = (
            ", u.must_change_password, "
            "CAST(u.terms_accepted_at AS datetime2) AS terms_accepted_at, "
            "u.terms_accepted_ip, u.terms_version"
        )
    with cursor(commit=False) as cur:
        cur.execute(
            f"""
            SELECT u.id, u.username, u.email, u.full_name, u.is_active, u.is_super_admin,
                   CAST(u.created_at AS datetime2) AS created_at,
                   CAST(u.updated_at AS datetime2) AS updated_at,
                   CAST(u.last_login_at AS datetime2) AS last_login_at,
                   COALESCE(ur.role_code, CASE WHEN u.is_super_admin = 1 THEN N'super_admin' ELSE N'viewer' END) AS role
                   {extra}
            FROM dbo.karta_user u
            LEFT JOIN dbo.karta_user_role ur ON ur.user_id = u.id
            ORDER BY u.username
            """
        )
        rows = rows_to_dicts(cur)
    if onboard:
        for row in rows:
            flags = _onboarding_flags_from_row(row)
            row["must_change_password"] = flags["must_change_password"]
            row["terms_accepted"] = flags["terms_accepted"]
    return rows


def get_user(user_id: int) -> dict[str, Any] | None:
    if not tables_available():
        return None
    onboard = onboarding_available()
    extra = ""
    if onboard:
        extra = (
            ", u.must_change_password, "
            "CAST(u.terms_accepted_at AS datetime2) AS terms_accepted_at, "
            "u.terms_accepted_ip, u.terms_version"
        )
    with cursor(commit=False) as cur:
        cur.execute(
            f"""
            SELECT u.id, u.username, u.email, u.full_name, u.is_active, u.is_super_admin,
                   COALESCE(ur.role_code, CASE WHEN u.is_super_admin = 1 THEN N'super_admin' ELSE N'viewer' END) AS role
                   {extra}
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
        if onboard:
            data.update(_onboarding_flags_from_row(data))
        return data


def create_email_verification_token(user_id: int) -> str | None:
    if not email_verification_available():
        return None
    token, hashed = new_verification_token()
    with cursor() as cur:
        cur.execute(
            """
            UPDATE dbo.karta_user
            SET email_verified_at = NULL,
                email_verification_token_hash = ?,
                email_verification_sent_at = SYSDATETIMEOFFSET(),
                email_verification_expires_at = ?,
                updated_at = SYSDATETIMEOFFSET()
            WHERE id = ? AND email IS NOT NULL
            """,
            hashed,
            expiry_utc(),
            int(user_id),
        )
        if cur.rowcount == 0:
            return None
    return token


def verify_email_token(token: str) -> dict[str, Any] | None:
    if not email_verification_available():
        return None
    hashed = token_hash(token)
    with cursor() as cur:
        cur.execute(
            """
            SELECT TOP (1) id, username, email, full_name
            FROM dbo.karta_user
            WHERE email_verification_token_hash = ?
              AND email_verification_expires_at >= SYSDATETIMEOFFSET()
            """,
            hashed,
        )
        row = cur.fetchone()
        data = row_to_dict(cur, row) if row else None
        if not data:
            return None
        cur.execute(
            """
            UPDATE dbo.karta_user
            SET email_verified_at = SYSDATETIMEOFFSET(),
                email_verification_token_hash = NULL,
                email_verification_expires_at = NULL,
                updated_at = SYSDATETIMEOFFSET()
            WHERE id = ?
            """,
            int(data["id"]),
        )
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
    must_change_password: bool = True,
) -> int:
    role_code = normalize_role(role)
    onboard = onboarding_available()
    with cursor() as cur:
        if onboard:
            cur.execute(
                """
                INSERT INTO dbo.karta_user (
                    username, email, password_hash, full_name, is_active, is_super_admin,
                    must_change_password
                )
                OUTPUT INSERTED.id
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                username.strip(),
                (email or "").strip() or None,
                generate_password_hash(password or "", method=_PASSWORD_HASH_METHOD),
                (full_name or "").strip() or None,
                1 if is_active else 0,
                1 if role_code == "super_admin" else 0,
                1 if must_change_password else 0,
            )
        else:
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


def is_super_admin_user(user: dict[str, Any] | None) -> bool:
    if not user:
        return False
    if bool(user.get("is_super_admin")):
        return True
    return str(user.get("role") or "").strip().lower() == "super_admin"


def count_super_admin_users() -> int:
    if not tables_available():
        return 0
    with cursor(commit=False) as cur:
        cur.execute(
            """
            SELECT COUNT(*)
            FROM dbo.karta_user u
            LEFT JOIN dbo.karta_user_role ur ON ur.user_id = u.id
            WHERE u.is_super_admin = 1
               OR ur.role_code = N'super_admin'
            """
        )
        row = cur.fetchone()
        return int(row[0]) if row else 0


def delete_user(user_id: int) -> bool:
    """Διαγράφει τον χρήστη και όλες τις συσχετίσεις ρόλου/δικαιωμάτων/καταστημάτων."""
    if not tables_available():
        return False
    uid = int(user_id)
    with cursor() as cur:
        cur.execute("SELECT id FROM dbo.karta_user WHERE id = ?", uid)
        if not cur.fetchone():
            return False
        cur.execute("DELETE FROM dbo.karta_user_permission WHERE user_id = ?", uid)
        cur.execute("DELETE FROM dbo.karta_user_store WHERE user_id = ?", uid)
        cur.execute("DELETE FROM dbo.karta_user_role WHERE user_id = ?", uid)
        cur.execute("DELETE FROM dbo.karta_user WHERE id = ?", uid)
    return True


def reset_password(user_id: int, password: str, *, must_change_password: bool = True) -> None:
    with cursor() as cur:
        if onboarding_available():
            cur.execute(
                """
                UPDATE dbo.karta_user
                SET password_hash = ?,
                    must_change_password = ?,
                    updated_at = SYSDATETIMEOFFSET()
                WHERE id = ?
                """,
                generate_password_hash(password or "", method=_PASSWORD_HASH_METHOD),
                1 if must_change_password else 0,
                int(user_id),
            )
        else:
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
