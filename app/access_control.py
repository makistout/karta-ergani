"""Role-based access control for office users."""

from __future__ import annotations

from dataclasses import dataclass
from fnmatch import fnmatch
from typing import Any

from flask import Flask, session

SESSION_ROLE = "office_role"
SESSION_USER_ID = "office_user_id"
SESSION_PERMISSIONS = "office_permissions"
SESSION_SUPER_ADMIN = "office_super_admin"

MANAGED_PERMISSION_CODES: set[str] = {
    "employees.sync",
    "employees.export",
    "schedule.export",
    "work_log.export",
    "stores.view_sensitive",
    "logs.view_errors",
    "logs.export",
    "users.view",
    "users.create",
    "users.edit",
    "users.disable",
    "users.reset_password",
    "users.manage_permissions",
    "users.manage_store_access",
    "settings.view",
    "settings.edit",
    "settings.secrets.manage",
    "settings.scheduler.manage",
}


@dataclass(frozen=True)
class RouteRule:
    method: str
    pattern: str
    permission: str


VIEWER_PERMISSIONS: set[str] = {
    "dashboard.view",
    "employees.view",
    "schedule.view",
    "work_log.view",
    "missing_cards.view",
    "work_card.view",
    "logs.view",
    "logs.view_sync",
    "logs.view_work_cards",
    "stores.view",
    "stores.select",
    "ergani.catalog",
}

OFFICE_OPERATOR_PERMISSIONS: set[str] = VIEWER_PERMISSIONS | {
    "sync.view",
    "sync.run_store",
    "sync.view_progress",
    "work_log.sync",
    "schedule.sync",
    "monthly_status.view",
    "monthly_status.sync",
    "work_card.submit_live",
    "work_card.submit_retro",
    "work_card.view_history",
    "work_card.sync_refresh",
    "missing_cards.close_one",
    "missing_cards.close_all",
    "missing_cards.sync_refresh",
    "schedule.submit_leave",
    "schedule.submit_daily",
    "schedule.submit_weekly",
}

STORE_MANAGER_PERMISSIONS: set[str] = OFFICE_OPERATOR_PERMISSIONS | {
    "notifications.view",
    "notifications.snooze",
    "notifications.send_test",
    "logs.view_notifications",
}

BACKOFFICE_ADMIN_PERMISSIONS: set[str] = STORE_MANAGER_PERMISSIONS | {
    "sync.run_period",
    "notifications.recipients.manage",
    "notifications.rules.manage",
    "stores.manage",
    "stores.api_env.manage",
}

ROLE_PERMISSIONS: dict[str, set[str]] = {
    "super_admin": {"*"},
    "admin": BACKOFFICE_ADMIN_PERMISSIONS,
    "backoffice_admin": BACKOFFICE_ADMIN_PERMISSIONS,
    "office_manager": STORE_MANAGER_PERMISSIONS,
    "office": OFFICE_OPERATOR_PERMISSIONS,
    "store_viewer": VIEWER_PERMISSIONS,
    "viewer": VIEWER_PERMISSIONS,
    "notifications_manager": {
        "dashboard.view",
        "stores.view",
        "stores.select",
        "notifications.view",
        "notifications.recipients.manage",
        "notifications.rules.manage",
        "notifications.snooze",
        "notifications.send_test",
        "logs.view",
        "logs.view_notifications",
    },
}

DEFAULT_ROLE = "super_admin"

UI_PERMISSIONS: dict[str, str] = {
    "/ui/": "dashboard.view",
    "/ui/stores": "stores.view",
    "/ui/stores/credentials": "stores.credentials.manage",
    "/ui/stores/notify": "notifications.view",
    "/ui/stores/branch": "stores.manage",
    "/ui/stores/mappings": "stores.manage",
    "/ui/employees": "employees.view",
    "/ui/employees/weekly-schedule": "schedule.view",
    "/ui/schedule": "schedule.view",
    "/ui/work-log": "work_log.view",
    "/ui/work-log/history": "work_log.view",
    "/ui/missing-cards": "missing_cards.view",
    "/ui/missing-cards/close-all": "missing_cards.close_all",
    "/ui/monthly-status": "monthly_status.view",
    "/ui/work-card": "work_card.view",
    "/ui/sync": "sync.view",
    "/ui/sync-log": "logs.view",
    "/ui/users": "users.view",
}

NAV_ITEMS: tuple[dict[str, str], ...] = (
    {"href": "/ui/", "nav": "home", "label": "Αρχική", "permission": "dashboard.view"},
    {"href": "/ui/employees", "nav": "employees", "label": "Εργαζόμενοι", "permission": "employees.view"},
    {"href": "/ui/schedule", "nav": "schedule", "label": "Ψηφιακό ωράριο", "permission": "schedule.view"},
    {"href": "/ui/work-log", "nav": "worklog", "label": "Πραγματική απασχόληση", "permission": "work_log.view"},
    {"href": "/ui/missing-cards", "nav": "missingcards", "label": "Ελλειπή Χτυπήματα", "permission": "missing_cards.view"},
    {"href": "/ui/work-card", "nav": "workcard", "label": "Ψηφιακή κάρτα", "permission": "work_card.view"},
    {"href": "/ui/sync", "nav": "sync", "label": "Συγχρονισμός", "permission": "sync.view"},
    {"href": "/ui/stores", "nav": "stores", "label": "Καταστήματα", "permission": "stores.view"},
    {"href": "/ui/stores/notify", "nav": "storenotify", "label": "Ειδοποιήσεις", "permission": "notifications.view"},
    {"href": "/ui/sync-log", "nav": "synclog", "label": "Καταγραφές", "permission": "logs.view"},
    {"href": "/ui/users", "nav": "users", "label": "Χρήστες", "permission": "users.view"},
)

API_RULES: tuple[RouteRule, ...] = (
    RouteRule("GET", "/api", "dashboard.view"),
    RouteRule("GET", "/api/dashboard/*", "dashboard.view"),
    RouteRule("GET", "/api/employees/*", "employees.view"),
    RouteRule("GET", "/api/store/list", "stores.view"),
    RouteRule("GET", "/api/store/active", "stores.view"),
    RouteRule("GET", "/api/store/select/status/*", "stores.view"),
    RouteRule("GET", "/api/store/*/notify-recipients", "notifications.view"),
    RouteRule("PUT", "/api/store/*/notify-recipients", "notifications.recipients.manage"),
    RouteRule("GET", "/api/store/*", "stores.credentials.manage"),
    RouteRule("POST", "/api/store/verify-*", "stores.credentials.manage"),
    RouteRule("POST", "/api/store/credentials", "stores.credentials.manage"),
    RouteRule("POST", "/api/store/save", "stores.manage"),
    RouteRule("POST", "/api/store/record-sync", "stores.manage"),
    RouteRule("POST", "/api/store/select", "stores.select"),
    RouteRule("DELETE", "/api/store/*", "stores.manage"),
    RouteRule("GET", "/api/schedule/*", "schedule.view"),
    RouteRule("POST", "/api/schedule/sync", "schedule.sync"),
    RouteRule("GET", "/api/work-log/list", "work_log.view"),
    RouteRule("GET", "/api/work-log/history", "work_log.view"),
    RouteRule("GET", "/api/work-log/missing-cards", "missing_cards.view"),
    RouteRule("GET", "/api/work-log/missing-cards/close-all-plan", "missing_cards.close_all"),
    RouteRule("POST", "/api/work-log/sync", "work_log.sync"),
    RouteRule("GET", "/api/work-log/sync/status/*", "work_log.view"),
    RouteRule("GET", "/api/monthly-status/*", "monthly_status.view"),
    RouteRule("POST", "/api/monthly-status/sync", "monthly_status.sync"),
    RouteRule("GET", "/api/work-card/*", "work_card.view"),
    RouteRule("POST", "/api/work-card/submit", "work_card.submit_live"),
    RouteRule("POST", "/api/leave/submit", "schedule.submit_leave"),
    RouteRule("GET", "/api/leave/types", "schedule.submit_leave"),
    RouteRule("GET", "/api/wto-week/availability", "schedule.submit_weekly"),
    RouteRule("POST", "/api/wto-daily/submit", "schedule.submit_daily"),
    RouteRule("POST", "/api/wto-week/submit", "schedule.submit_weekly"),
    RouteRule("POST", "/api/ergani/sync-all", "sync.run_all"),
    RouteRule("GET", "/api/ergani/sync-all/status/*", "sync.view_progress"),
    RouteRule("POST", "/api/period-sync/run", "sync.run_period"),
    RouteRule("GET", "/api/period-sync/run/status/*", "sync.view_progress"),
    RouteRule("GET", "/api/sync-log/runs*", "logs.view_sync"),
    RouteRule("GET", "/api/sync-log/notifications*", "logs.view_notifications"),
    RouteRule("GET", "/api/audit/*", "logs.view"),
    RouteRule("GET", "/api/ergani/branches", "ergani.catalog"),
    RouteRule("GET", "/api/ergani/catalog/*", "ergani.catalog"),
    RouteRule("GET", "/api/ergani/kallikratis/search", "ergani.catalog"),
    RouteRule("POST", "/api/ergani/auth/authenticate", "stores.credentials.manage"),
    RouteRule("GET", "/api/local/*", "work_card.view"),
    RouteRule("POST", "/api/local/work-card/event", "work_card.submit_live"),
    RouteRule("POST", "/api/telegram/test/*", "notifications.send_test"),
    RouteRule("POST", "/api/telegram/notify/*", "notifications.send_test"),
    RouteRule("GET", "/api/users", "users.view"),
    RouteRule("POST", "/api/users/*/password", "users.reset_password"),
    RouteRule("PUT", "/api/users/*/permissions", "users.manage_permissions"),
    RouteRule("PUT", "/api/users/*/stores", "users.manage_store_access"),
    RouteRule("GET", "/api/users/*", "users.view"),
    RouteRule("POST", "/api/users", "users.create"),
    RouteRule("PUT", "/api/users/*", "users.edit"),
)


def normalize_role(role: str | None) -> str:
    value = (role or DEFAULT_ROLE).strip().lower()
    return value if value in ROLE_PERMISSIONS else DEFAULT_ROLE


def permissions_for_role(role: str | None) -> set[str]:
    return set(ROLE_PERMISSIONS[normalize_role(role)])


def current_role() -> str:
    return normalize_role(str(session.get(SESSION_ROLE) or DEFAULT_ROLE))


def has_permission(permission: str | None, *, role: str | None = None) -> bool:
    if not permission:
        return True
    if role is None:
        session_permissions = session.get(SESSION_PERMISSIONS)
        if isinstance(session_permissions, list):
            permissions = {str(x) for x in session_permissions}
            return "*" in permissions or permission in permissions
    permissions = permissions_for_role(role if role is not None else current_role())
    return "*" in permissions or permission in permissions


def current_permissions() -> set[str]:
    session_permissions = session.get(SESSION_PERMISSIONS)
    if isinstance(session_permissions, list):
        return {str(x) for x in session_permissions}
    return permissions_for_role(current_role())


def is_super_admin() -> bool:
    return bool(session.get(SESSION_SUPER_ADMIN)) or "*" in current_permissions()


def current_user_id() -> int | None:
    raw = session.get(SESSION_USER_ID)
    try:
        return int(raw) if raw is not None else None
    except (TypeError, ValueError):
        return None


def can_access_store(store_id: int | None) -> bool:
    if not store_id:
        return False
    if is_super_admin():
        return True
    try:
        from app.repo_users import user_can_access_store

        return user_can_access_store(
            current_user_id(),
            int(store_id),
            is_super_admin=is_super_admin(),
        )
    except Exception:
        return True


def accessible_store_ids() -> set[int] | None:
    if is_super_admin():
        return None
    try:
        from app.repo_users import accessible_store_ids as repo_accessible_store_ids

        return repo_accessible_store_ids(current_user_id(), is_super_admin=is_super_admin())
    except Exception:
        return None


def all_permission_codes() -> list[str]:
    codes: set[str] = {"*"} | MANAGED_PERMISSION_CODES
    for permissions in ROLE_PERMISSIONS.values():
        codes.update(permissions)
    for permission in UI_PERMISSIONS.values():
        codes.add(permission)
    for rule in API_RULES:
        codes.add(rule.permission)
    return sorted(codes)


def permission_for_path(path: str, method: str) -> str | None:
    norm = (path or "").strip() or "/"
    if len(norm) > 1 and norm.endswith("/"):
        norm = norm.rstrip("/")
    verb = (method or "GET").upper()
    if norm.startswith("/ui/") or norm == "/ui":
        return UI_PERMISSIONS.get(norm if norm != "/ui" else "/ui/")
    for rule in API_RULES:
        if rule.method != verb:
            continue
        if fnmatch(norm, rule.pattern):
            return rule.permission
    return None


def user_payload(username: str | None = None, role: str | None = None) -> dict[str, Any]:
    resolved_role = normalize_role(role if role is not None else current_role())
    permissions = current_permissions() if role is None else permissions_for_role(resolved_role)
    return {
        "user": username,
        "role": resolved_role,
        "is_super_admin": "*" in permissions,
        "permissions": sorted(permissions),
    }


def register_access_context(app: Flask) -> None:
    @app.context_processor
    def _access_context():
        return {
            "office_nav_items": NAV_ITEMS,
            "office_role": current_role,
            "office_has_permission": has_permission,
        }
