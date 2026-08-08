"""Στοιχεία σύμβασης προσωπικού — append-only snapshots (portal Μητρώα)."""

from __future__ import annotations

import hashlib
import json
from typing import Any

import pyodbc

from app.db import cursor
from app.row_util import rows_to_dicts
from app.work_card_payload import norm_afm

_TRACKED_FIELDS = (
    "specialty",
    "characterization",
    "step92",
    "weekly_work_days",
    "prior_service",
    "employment_relation",
    "fixed_term_from",
    "fixed_term_to",
    "regime",
    "weekly_hours",
    "salary",
    "hourly_wage",
    "total_weekly_hours",
    "fulltime_contract_weekly_hours",
    "break_minutes",
    "break_in_work",
    "flex_arrival_minutes",
    "ergani_updated_at",
)


def employment_contract_table_missing_message(exc: BaseException) -> str | None:
    if isinstance(exc, pyodbc.Error):
        err = exc.args[0] if exc.args else ""
        if err == "42S02" or "karta_employment_contract" in str(exc):
            return (
                "Λείπει ο πίνακας karta_employment_contract στη βάση. "
                "Τρέξτε το sql/alter_add_karta_employment_contract.sql ή "
                "python scripts/ensure_karta_employment_contract_table.py."
            )
    return None


def _norm_str(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _norm_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def content_hash_for_contract(row: dict[str, Any]) -> str:
    payload = {
        key: (
            _norm_int(row.get(key))
            if key in ("break_minutes", "break_in_work", "flex_arrival_minutes")
            else _norm_str(row.get(key))
        )
        for key in _TRACKED_FIELDS
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _normalize_row(
    employer_afm: str,
    branch_aa: str,
    row: dict[str, Any],
) -> dict[str, Any]:
    employee_afm = norm_afm(row.get("employee_afm") or "")
    out = {
        "employer_afm": norm_afm(employer_afm),
        "branch_aa": str(branch_aa or "0").strip()[:32] or "0",
        "employee_afm": employee_afm,
        "eponymo": _norm_str(row.get("eponymo"))[:200] or None,
        "onoma": _norm_str(row.get("onoma"))[:200] or None,
        "specialty": _norm_str(row.get("specialty"))[:200] or None,
        "characterization": _norm_str(row.get("characterization"))[:200] or None,
        "step92": _norm_str(row.get("step92"))[:64] or None,
        "weekly_work_days": _norm_str(row.get("weekly_work_days"))[:64] or None,
        "prior_service": _norm_str(row.get("prior_service"))[:64] or None,
        "employment_relation": _norm_str(row.get("employment_relation"))[:200] or None,
        "fixed_term_from": _norm_str(row.get("fixed_term_from"))[:32] or None,
        "fixed_term_to": _norm_str(row.get("fixed_term_to"))[:32] or None,
        "regime": _norm_str(row.get("regime"))[:200] or None,
        "weekly_hours": _norm_str(row.get("weekly_hours"))[:32] or None,
        "salary": _norm_str(row.get("salary"))[:64] or None,
        "hourly_wage": _norm_str(row.get("hourly_wage"))[:64] or None,
        "total_weekly_hours": _norm_str(row.get("total_weekly_hours"))[:32] or None,
        "fulltime_contract_weekly_hours": _norm_str(
            row.get("fulltime_contract_weekly_hours")
        )[:32]
        or None,
        "break_minutes": _norm_int(row.get("break_minutes")),
        "break_in_work": _norm_int(row.get("break_in_work")),
        "flex_arrival_minutes": _norm_int(row.get("flex_arrival_minutes")),
        "ergani_updated_at": _norm_str(row.get("ergani_updated_at"))[:32] or None,
        "source": _norm_str(row.get("source"))[:16] or "portal",
    }
    out["content_hash"] = content_hash_for_contract(out)
    return out


def latest_for_employee(
    employer_afm: str,
    branch_aa: str,
    employee_afm: str,
) -> dict[str, Any] | None:
    afm = norm_afm(employer_afm)
    aa = str(branch_aa or "0").strip()[:32] or "0"
    e_afm = norm_afm(employee_afm)
    if not e_afm:
        return None
    with cursor(commit=False) as cur:
        cur.execute(
            """
            SELECT TOP (1)
                id, employer_afm, branch_aa, employee_afm, eponymo, onoma,
                specialty, characterization, step92, weekly_work_days, prior_service,
                employment_relation, fixed_term_from, fixed_term_to, regime,
                weekly_hours, salary, hourly_wage, total_weekly_hours,
                fulltime_contract_weekly_hours, break_minutes, break_in_work,
                flex_arrival_minutes, ergani_updated_at, content_hash, is_current,
                CAST(synced_at AS datetime2) AS synced_at, source
            FROM dbo.karta_employment_contract
            WHERE employer_afm = ? AND branch_aa = ? AND employee_afm = ?
              AND is_current = 1
            ORDER BY id DESC
            """,
            (afm, aa, e_afm),
        )
        rows = rows_to_dicts(cur)
        return rows[0] if rows else None


def insert_if_changed(
    employer_afm: str,
    branch_aa: str,
    row: dict[str, Any],
) -> dict[str, Any]:
    """Εισάγει νέο snapshot αν άλλαξε hash ή ergani_updated_at. Επιστρέφει {inserted, id?}."""
    data = _normalize_row(employer_afm, branch_aa, row)
    if not data["employee_afm"]:
        return {"inserted": False, "reason": "missing_employee_afm"}

    previous = latest_for_employee(
        data["employer_afm"], data["branch_aa"], data["employee_afm"]
    )
    if previous:
        prev_hash = _norm_str(previous.get("content_hash"))
        if prev_hash and prev_hash == data["content_hash"]:
            return {"inserted": False, "reason": "unchanged", "id": previous.get("id")}

    with cursor() as cur:
        if previous:
            cur.execute(
                """
                UPDATE dbo.karta_employment_contract
                SET is_current = 0
                WHERE employer_afm = ? AND branch_aa = ? AND employee_afm = ?
                  AND is_current = 1
                """,
                (data["employer_afm"], data["branch_aa"], data["employee_afm"]),
            )
        cur.execute(
            """
            INSERT INTO dbo.karta_employment_contract (
                employer_afm, branch_aa, employee_afm, eponymo, onoma,
                specialty, characterization, step92, weekly_work_days, prior_service,
                employment_relation, fixed_term_from, fixed_term_to, regime,
                weekly_hours, salary, hourly_wage, total_weekly_hours,
                fulltime_contract_weekly_hours, break_minutes, break_in_work,
                flex_arrival_minutes, ergani_updated_at, content_hash,
                is_current, source
            ) OUTPUT INSERTED.id
            VALUES (
                ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?,
                ?, ?, ?, ?,
                ?, ?, ?, ?,
                ?, ?, ?,
                ?, ?, ?,
                1, ?
            )
            """,
            (
                data["employer_afm"],
                data["branch_aa"],
                data["employee_afm"],
                data["eponymo"],
                data["onoma"],
                data["specialty"],
                data["characterization"],
                data["step92"],
                data["weekly_work_days"],
                data["prior_service"],
                data["employment_relation"],
                data["fixed_term_from"],
                data["fixed_term_to"],
                data["regime"],
                data["weekly_hours"],
                data["salary"],
                data["hourly_wage"],
                data["total_weekly_hours"],
                data["fulltime_contract_weekly_hours"],
                data["break_minutes"],
                data["break_in_work"],
                data["flex_arrival_minutes"],
                data["ergani_updated_at"],
                data["content_hash"],
                data["source"],
            ),
        )
        new_id = cur.fetchone()[0]
    return {"inserted": True, "id": int(new_id), "content_hash": data["content_hash"]}


def delete_all_for_store(employer_afm: str, branch_aa: str | None = None) -> int:
    """Διαγραφή snapshots σύμβασης για κατάστημα (ή όλα τα παραρτήματα αν branch_aa=None)."""
    afm = norm_afm(employer_afm)
    with cursor() as cur:
        if branch_aa is None:
            cur.execute(
                "DELETE FROM dbo.karta_employment_contract WHERE employer_afm = ?",
                (afm,),
            )
        else:
            aa = str(branch_aa or "0").strip()[:32] or "0"
            cur.execute(
                """
                DELETE FROM dbo.karta_employment_contract
                WHERE employer_afm = ? AND branch_aa = ?
                """,
                (afm, aa),
            )
        return int(cur.rowcount or 0)


def list_current_for_store(
    employer_afm: str,
    branch_aa: str,
    limit: int = 5000,
) -> list[dict[str, Any]]:
    lim = max(1, min(int(limit), 10000))
    afm = norm_afm(employer_afm)
    aa = str(branch_aa or "0").strip()[:32] or "0"
    with cursor(commit=False) as cur:
        cur.execute(
            f"""
            SELECT TOP ({lim})
                id, employer_afm, branch_aa, employee_afm, eponymo, onoma,
                specialty, characterization, step92, weekly_work_days, prior_service,
                employment_relation, fixed_term_from, fixed_term_to, regime,
                weekly_hours, salary, hourly_wage, total_weekly_hours,
                fulltime_contract_weekly_hours, break_minutes, break_in_work,
                flex_arrival_minutes, ergani_updated_at, content_hash, is_current,
                CAST(synced_at AS datetime2) AS synced_at, source
            FROM dbo.karta_employment_contract
            WHERE employer_afm = ? AND branch_aa = ? AND is_current = 1
            ORDER BY eponymo, onoma, employee_afm
            """,
            (afm, aa),
        )
        return rows_to_dicts(cur)


def list_history_for_employee(
    employer_afm: str,
    branch_aa: str,
    employee_afm: str,
    limit: int = 200,
) -> list[dict[str, Any]]:
    lim = max(1, min(int(limit), 1000))
    afm = norm_afm(employer_afm)
    aa = str(branch_aa or "0").strip()[:32] or "0"
    e_afm = norm_afm(employee_afm)
    if not e_afm:
        return []
    with cursor(commit=False) as cur:
        cur.execute(
            f"""
            SELECT TOP ({lim})
                id, employer_afm, branch_aa, employee_afm, eponymo, onoma,
                specialty, characterization, step92, weekly_work_days, prior_service,
                employment_relation, fixed_term_from, fixed_term_to, regime,
                weekly_hours, salary, hourly_wage, total_weekly_hours,
                fulltime_contract_weekly_hours, break_minutes, break_in_work,
                flex_arrival_minutes, ergani_updated_at, content_hash, is_current,
                CAST(synced_at AS datetime2) AS synced_at, source
            FROM dbo.karta_employment_contract
            WHERE employer_afm = ? AND branch_aa = ? AND employee_afm = ?
            ORDER BY synced_at DESC, id DESC
            """,
            (afm, aa, e_afm),
        )
        return rows_to_dicts(cur)
