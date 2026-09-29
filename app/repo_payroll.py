"""Παράμετροι μισθοδοσίας — dated key/value ανά εταιρεία (store_id=0) ή κατάστημα."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

import pyodbc

from app.db import cursor
from app.payroll import (
    MINIMUM_WAGE_HISTORY,
    EFKA_CEILING_HISTORY,
    PARAMETER_CATALOG,
    default_parameter_map,
    resolve_parameters,
)
from app.row_util import rows_to_dicts

DB_SETUP = "sql/alter_add_karta_payroll_parameter.sql"
COMPANY_STORE_ID = 0


def table_missing_message(exc: BaseException) -> str | None:
    if isinstance(exc, pyodbc.Error):
        err = exc.args[0] if exc.args else ""
        if err == "42S02" or "karta_payroll_parameter" in str(exc):
            return (
                "Λείπει ο πίνακας karta_payroll_parameter. "
                "Τρέξτε python scripts/ensure_karta_payroll_parameter_table.py"
            )
    return None


def tables_available() -> bool:
    try:
        with cursor(commit=False) as cur:
            cur.execute(
                "SELECT 1 FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = ?",
                ("karta_payroll_parameter",),
            )
            return cur.fetchone() is not None
    except pyodbc.Error:
        return False


def _row_to_public(row: dict[str, Any]) -> dict[str, Any]:
    catalog = next((item for item in PARAMETER_CATALOG if item["code"] == row.get("code")), None)
    valid_from = row.get("valid_from")
    valid_to = row.get("valid_to")
    if isinstance(valid_from, datetime):
        valid_from = valid_from.date()
    if isinstance(valid_to, datetime):
        valid_to = valid_to.date()
    return {
        "id": row.get("id"),
        "store_id": int(row.get("store_id") or 0),
        "code": row.get("code"),
        "value": row.get("value"),
        "value_kind": row.get("value_kind") or (catalog or {}).get("value_kind"),
        "valid_from": valid_from.isoformat() if hasattr(valid_from, "isoformat") else str(valid_from or ""),
        "valid_to": valid_to.isoformat() if hasattr(valid_to, "isoformat") and valid_to else None,
        "label": row.get("label") or (catalog or {}).get("label"),
        "group_code": row.get("group_code") or (catalog or {}).get("group_code"),
        "group_label": (catalog or {}).get("group_label") or row.get("group_code"),
        "sort_order": int(row.get("sort_order") or (catalog or {}).get("sort_order") or 0),
        "legal_ref": row.get("legal_ref") or (catalog or {}).get("legal_ref") or "",
        "note": row.get("note") or (catalog or {}).get("note") or "",
        "updated_at": str(row.get("updated_at") or ""),
        "updated_by": row.get("updated_by") or "",
        "choices": (catalog or {}).get("choices"),
    }


def public_parameter_rows(store_id: int | None = None) -> list[dict[str, Any]]:
    return [_row_to_public(row) for row in list_parameter_rows(store_id)]


def list_parameter_rows(store_id: int | None = None) -> list[dict[str, Any]]:
    if not tables_available():
        return []
    with cursor(commit=False) as cur:
        if store_id is None:
            cur.execute(
                """
                SELECT id, store_id, code, value, value_kind, valid_from, valid_to,
                       label, group_code, sort_order, legal_ref, note, updated_at, updated_by
                FROM dbo.karta_payroll_parameter
                ORDER BY group_code, sort_order, code, valid_from, store_id
                """
            )
        else:
            cur.execute(
                """
                SELECT id, store_id, code, value, value_kind, valid_from, valid_to,
                       label, group_code, sort_order, legal_ref, note, updated_at, updated_by
                FROM dbo.karta_payroll_parameter
                WHERE store_id IN (0, ?)
                ORDER BY group_code, sort_order, code, valid_from, store_id
                """,
                int(store_id),
            )
        return rows_to_dicts(cur)


def load_resolved(*, store_id: int = 0, as_of: date | None = None) -> dict[str, str]:
    rows = list_parameter_rows(store_id)
    if not rows:
        return default_parameter_map()
    return resolve_parameters(rows, store_id=store_id, as_of=as_of)


_WAGE_CODES = {"min_monthly_salary", "min_daily_wage"}
_DATED_CODES = _WAGE_CODES | {"efka_monthly_ceiling"}


def ensure_seeded() -> None:
    """Γεμίζει εταιρικές προεπιλογές και εισάγει νέους κωδικούς καταλόγου που λείπουν."""
    if not tables_available():
        return
    with cursor() as cur:
        cur.execute(
            "SELECT DISTINCT code FROM dbo.karta_payroll_parameter WHERE store_id = ?",
            COMPANY_STORE_ID,
        )
        existing = {str(row[0]) for row in cur.fetchall()}
        valid_from = date(2000, 1, 1)
        if not existing:
            for item in PARAMETER_CATALOG:
                if item["code"] in _DATED_CODES:
                    continue
                _insert_row(
                    cur, item, store_id=COMPANY_STORE_ID, value=str(item["default"]),
                    valid_from=valid_from, updated_by="seed",
                )
            for wage in MINIMUM_WAGE_HISTORY:
                start = datetime.strptime(wage["valid_from"], "%Y-%m-%d").date()
                for code in ("min_monthly_salary", "min_daily_wage"):
                    catalog = next(item for item in PARAMETER_CATALOG if item["code"] == code)
                    _insert_row(
                        cur, catalog, store_id=COMPANY_STORE_ID, value=wage[code],
                        valid_from=start, updated_by="seed", legal_ref=wage["legal_ref"],
                    )
            _seed_efka_ceiling(cur)
            return
        for item in PARAMETER_CATALOG:
            if item["code"] in existing or item["code"] in _DATED_CODES:
                continue
            _insert_row(
                cur, item, store_id=COMPANY_STORE_ID, value=str(item["default"]),
                valid_from=valid_from, updated_by="seed",
            )
        if "efka_monthly_ceiling" not in existing:
            _seed_efka_ceiling(cur)


def _seed_efka_ceiling(cur: Any) -> None:
    catalog = next(item for item in PARAMETER_CATALOG if item["code"] == "efka_monthly_ceiling")
    for row in EFKA_CEILING_HISTORY:
        start = datetime.strptime(row["valid_from"], "%Y-%m-%d").date()
        _insert_row(
            cur, catalog, store_id=COMPANY_STORE_ID, value=row["efka_monthly_ceiling"],
            valid_from=start, updated_by="seed", legal_ref=row["legal_ref"],
        )


def _insert_row(
    cur: Any,
    catalog: dict[str, Any],
    *,
    store_id: int,
    value: str,
    valid_from: date,
    updated_by: str | None,
    legal_ref: str | None = None,
    note: str | None = None,
) -> None:
    cur.execute(
        """
        INSERT INTO dbo.karta_payroll_parameter (
            store_id, code, value, value_kind, valid_from, valid_to,
            label, group_code, sort_order, legal_ref, note, updated_by
        ) VALUES (?, ?, ?, ?, ?, NULL, ?, ?, ?, ?, ?, ?)
        """,
        int(store_id),
        str(catalog["code"]),
        str(value),
        str(catalog.get("value_kind") or "text"),
        valid_from,
        str(catalog.get("label") or catalog["code"]),
        str(catalog.get("group_code") or "custom"),
        int(catalog.get("sort_order") or 900),
        str(legal_ref if legal_ref is not None else catalog.get("legal_ref") or ""),
        str(note if note is not None else catalog.get("note") or ""),
        str(updated_by or "")[:100] or None,
    )


def save_parameters(
    items: list[dict[str, Any]],
    *,
    store_id: int = 0,
    valid_from: date | None = None,
    updated_by: str | None = None,
) -> list[dict[str, Any]]:
    if not tables_available():
        raise LookupError("missing-table")
    ensure_seeded()
    start = valid_from or date.today()
    sid = int(store_id or 0)
    with cursor() as cur:
        for item in items:
            code = str(item.get("code") or "").strip()
            if not code:
                continue
            value = str(item.get("value") if item.get("value") is not None else "").strip()
            catalog = next((row for row in PARAMETER_CATALOG if row["code"] == code), None)
            if catalog is None:
                catalog = {
                    "code": code,
                    "label": str(item.get("label") or code),
                    "group_code": str(item.get("group_code") or "custom"),
                    "value_kind": str(item.get("value_kind") or "text"),
                    "sort_order": int(item.get("sort_order") or 900),
                    "legal_ref": str(item.get("legal_ref") or ""),
                    "note": str(item.get("note") or ""),
                }
            cur.execute(
                """
                SELECT TOP 1 id, value, valid_from
                FROM dbo.karta_payroll_parameter
                WHERE store_id = ? AND code = ? AND valid_to IS NULL
                ORDER BY valid_from DESC, id DESC
                """,
                sid,
                code,
            )
            current = cur.fetchone()
            if current is not None:
                current_from = current[2]
                if isinstance(current_from, datetime):
                    current_from = current_from.date()
                if current_from == start and str(current[1]) == value:
                    continue
                if current_from == start:
                    cur.execute(
                        """
                        UPDATE dbo.karta_payroll_parameter
                        SET value = ?, legal_ref = COALESCE(NULLIF(?, N''), legal_ref),
                            note = COALESCE(NULLIF(?, N''), note),
                            updated_at = SYSUTCDATETIME(), updated_by = ?
                        WHERE id = ?
                        """,
                        value,
                        str(item.get("legal_ref") or ""),
                        str(item.get("note") or ""),
                        str(updated_by or "")[:100] or None,
                        int(current[0]),
                    )
                    continue
                close_to = start - timedelta(days=1)
                if close_to >= current_from:
                    cur.execute(
                        "UPDATE dbo.karta_payroll_parameter SET valid_to = ? WHERE id = ?",
                        close_to,
                        int(current[0]),
                    )
            _insert_row(
                cur, catalog, store_id=sid, value=value, valid_from=start,
                updated_by=updated_by,
                legal_ref=str(item.get("legal_ref") or "") or None,
                note=str(item.get("note") or "") or None,
            )
    return [_row_to_public(row) for row in list_parameter_rows(sid)]
