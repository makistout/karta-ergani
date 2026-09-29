"""Στοιχεία σύμβασης προσωπικού — append-only snapshots (portal Μητρώα)."""

from __future__ import annotations

import hashlib
import json
from typing import Any

import pyodbc

from app.db import cursor
from app.row_util import rows_to_dicts
from app.employment_contract_parse import map_marital_status
from app.web_ma_payload import normalize_epikourikiki_kod, normalize_kyria_asfalish
from app.work_card_payload import norm_afm

_KEEP_IF_EMPTY = (
    "prior_service",
    "arithmos_teknon",
    "marital_status",
    "kyria_asfalish",
    "epikourikiki_kod",
)
_TRACKED_FIELDS = (
    "specialty",
    "characterization",
    "step92",
    "weekly_work_days",
    "prior_service",
    "arithmos_teknon",
    "marital_status",
    "kyria_asfalish",
    "epikourikiki_kod",
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
        "arithmos_teknon": _norm_str(row.get("arithmos_teknon"))[:16] or None,
        "marital_status": map_marital_status(row.get("marital_status"))[:32] or None,
        "kyria_asfalish": (
            normalize_kyria_asfalish(_norm_str(row.get("kyria_asfalish")))[:16]
            if _norm_str(row.get("kyria_asfalish"))
            else None
        ),
        "epikourikiki_kod": (
            normalize_epikourikiki_kod(_norm_str(row.get("epikourikiki_kod")))[:16]
            if _norm_str(row.get("epikourikiki_kod"))
            else None
        ),
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


def _merge_kept_personal(data: dict[str, Any], previous: dict[str, Any]) -> dict[str, Any]:
    """Το HTML του portal συχνά δεν έχει τέκνα/γάμο· μην τα σβήνεις από την τρέχουσα σύμβαση."""
    changed = False
    for key in _KEEP_IF_EMPTY:
        if data.get(key) or not previous.get(key):
            continue
        data[key] = previous.get(key)
        changed = True
    if changed:
        data["content_hash"] = content_hash_for_contract(data)
    return data


_CONTRACT_COLUMNS = """
                id, employer_afm, branch_aa, employee_afm, eponymo, onoma,
                specialty, characterization, step92, weekly_work_days, prior_service,
                arithmos_teknon, marital_status, kyria_asfalish, epikourikiki_kod,
                employment_relation, fixed_term_from, fixed_term_to, regime,
                weekly_hours, salary, hourly_wage, total_weekly_hours,
                fulltime_contract_weekly_hours, break_minutes, break_in_work,
                flex_arrival_minutes, ergani_updated_at, content_hash, is_current,
                CAST(synced_at AS datetime2) AS synced_at,
                CAST(last_checked_at AS datetime2) AS last_checked_at, source
"""


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
            f"""
            SELECT TOP (1)
            {_CONTRACT_COLUMNS}
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
        data = _merge_kept_personal(data, previous)
        prev_hash = _norm_str(previous.get("content_hash"))
        if prev_hash and prev_hash == data["content_hash"]:
            with cursor() as cur:
                cur.execute(
                    """
                    UPDATE dbo.karta_employment_contract
                    SET last_checked_at = SYSDATETIMEOFFSET()
                    WHERE id = ? AND is_current = 1
                    """,
                    (previous["id"],),
                )
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
                arithmos_teknon, marital_status, kyria_asfalish, epikourikiki_kod,
                employment_relation, fixed_term_from, fixed_term_to, regime,
                weekly_hours, salary, hourly_wage, total_weekly_hours,
                fulltime_contract_weekly_hours, break_minutes, break_in_work,
                flex_arrival_minutes, ergani_updated_at, content_hash,
                is_current, source, last_checked_at
            ) OUTPUT INSERTED.id
            VALUES (
                ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?,
                ?, ?, ?, ?,
                ?, ?, ?, ?,
                ?, ?, ?, ?,
                ?, ?, ?,
                ?, ?, ?,
                1, ?, SYSDATETIMEOFFSET()
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
                data["arithmos_teknon"],
                data["marital_status"],
                data["kyria_asfalish"],
                data["epikourikiki_kod"],
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
                arithmos_teknon, marital_status, kyria_asfalish, epikourikiki_kod,
                employment_relation, fixed_term_from, fixed_term_to, regime,
                weekly_hours, salary, hourly_wage, total_weekly_hours,
                fulltime_contract_weekly_hours, break_minutes, break_in_work,
                flex_arrival_minutes, ergani_updated_at, content_hash, is_current,
                CAST(synced_at AS datetime2) AS synced_at,
                CAST(last_checked_at AS datetime2) AS last_checked_at, source
            FROM dbo.karta_employment_contract
            WHERE employer_afm = ? AND branch_aa = ? AND is_current = 1
            ORDER BY eponymo, onoma, employee_afm
            """,
            (afm, aa),
        )
        return rows_to_dicts(cur)


def list_history_for_store(
    employer_afm: str, branch_aa: str, limit: int = 20000,
) -> list[dict[str, Any]]:
    """All contract snapshots used to resolve the contract effective per day."""
    lim = max(1, min(int(limit), 50000))
    afm = norm_afm(employer_afm)
    aa = str(branch_aa or "0").strip()[:32] or "0"
    with cursor(commit=False) as cur:
        cur.execute(
            f"""
            SELECT TOP ({lim})
                id, employer_afm, branch_aa, employee_afm, eponymo, onoma,
                specialty, characterization, step92, weekly_work_days, prior_service,
                arithmos_teknon, marital_status, kyria_asfalish, epikourikiki_kod,
                employment_relation, fixed_term_from, fixed_term_to, regime,
                weekly_hours, salary, hourly_wage, total_weekly_hours,
                fulltime_contract_weekly_hours, break_minutes, break_in_work,
                flex_arrival_minutes, ergani_updated_at, content_hash, is_current,
                CAST(synced_at AS datetime2) AS synced_at,
                CAST(last_checked_at AS datetime2) AS last_checked_at, source
            FROM dbo.karta_employment_contract
            WHERE employer_afm=? AND branch_aa=?
            ORDER BY employee_afm, synced_at, id
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
                arithmos_teknon, marital_status, kyria_asfalish, epikourikiki_kod,
                employment_relation, fixed_term_from, fixed_term_to, regime,
                weekly_hours, salary, hourly_wage, total_weekly_hours,
                fulltime_contract_weekly_hours, break_minutes, break_in_work,
                flex_arrival_minutes, ergani_updated_at, content_hash, is_current,
                CAST(synced_at AS datetime2) AS synced_at,
                CAST(last_checked_at AS datetime2) AS last_checked_at, source
            FROM dbo.karta_employment_contract
            WHERE employer_afm = ? AND branch_aa = ? AND employee_afm = ?
            ORDER BY synced_at DESC, id DESC
            """,
            (afm, aa, e_afm),
        )
        return rows_to_dicts(cur)


def _pick_personal(pers: dict[str, Any], latest: dict[str, Any], key: str) -> Any:
    val = pers.get(key)
    if val is None or str(val).strip() == "":
        return latest.get(key)
    return val


def apply_ex_base_05_personal(
    employer_afm: str,
    branch_aa: str,
    item: dict[str, Any],
) -> dict[str, Any] | None:
    """Ενημερώνει ταυτότητα (ΑΜΚΑ/ΑΜΑ/πρόσληψη) και προσωπικά σύμβασης από EX_BASE_05."""
    from app.web_ma_payload import personal_fields_from_ex_base_05

    afm = norm_afm(item.get("afm") or item.get("Afm") or "")
    if not afm:
        return None
    pers = personal_fields_from_ex_base_05(item)
    from app.ergani_parse import (
        hire_date_from_ergani_item,
        parse_ergani_calendar_date,
        parse_flex_arrival_minutes,
        parse_registry_digits,
    )
    from app.repo_entities import fill_employment_hire_date_if_empty, upsert_employee_by_afm

    hire = hire_date_from_ergani_item(item) or parse_ergani_calendar_date(
        pers.get("hire_date")
    )
    if hire:
        fill_employment_hire_date_if_empty(employer_afm, branch_aa, afm, hire)
    upsert_employee_by_afm(
        afm,
        pers.get("eponymo"),
        pers.get("onoma"),
        flex_arrival_minutes=parse_flex_arrival_minutes(item),
        amka=pers.get("amka") or parse_registry_digits(
            item, "Amka", "AMKA", "amka", max_len=11,
        ),
        amika=pers.get("amika") or parse_registry_digits(
            item, "AmIka", "AMIKA", "AmIKA", "amika", max_len=20,
        ),
    )
    latest = latest_for_employee(employer_afm, branch_aa, afm) or {}
    row = {
        "employee_afm": afm,
        "eponymo": _pick_personal(pers, latest, "eponymo") or latest.get("eponymo"),
        "onoma": _pick_personal(pers, latest, "onoma") or latest.get("onoma"),
        "specialty": _pick_personal(pers, latest, "specialty"),
        "characterization": _pick_personal(pers, latest, "characterization"),
        "step92": _pick_personal(pers, latest, "step92"),
        "weekly_work_days": _pick_personal(pers, latest, "weekly_work_days"),
        "prior_service": _pick_personal(pers, latest, "prior_service"),
        "arithmos_teknon": _pick_personal(pers, latest, "arithmos_teknon"),
        "marital_status": map_marital_status(
            item.get("MaritalStatus") or item.get("marital_status")
        ) or latest.get("marital_status"),
        "kyria_asfalish": _pick_personal(pers, latest, "kyria_asfalish"),
        "epikourikiki_kod": _pick_personal(pers, latest, "epikourikiki_kod"),
        "employment_relation": _pick_personal(pers, latest, "employment_relation"),
        "fixed_term_from": latest.get("fixed_term_from"),
        "fixed_term_to": latest.get("fixed_term_to"),
        "regime": _pick_personal(pers, latest, "regime"),
        "weekly_hours": _pick_personal(pers, latest, "weekly_hours"),
        "salary": _pick_personal(pers, latest, "salary"),
        "hourly_wage": _pick_personal(pers, latest, "hourly_wage"),
        "total_weekly_hours": latest.get("total_weekly_hours"),
        "fulltime_contract_weekly_hours": _pick_personal(
            pers, latest, "fulltime_contract_weekly_hours"
        ),
        "break_minutes": _pick_personal(pers, latest, "break_minutes"),
        "break_in_work": _pick_personal(pers, latest, "break_in_work"),
        "flex_arrival_minutes": _pick_personal(pers, latest, "flex_arrival_minutes"),
        "ergani_updated_at": latest.get("ergani_updated_at"),
        "source": latest.get("source") or "ergani",
    }
    return insert_if_changed(employer_afm, branch_aa, row)


def apply_ex_base_05_items(
    employer_afm: str,
    branch_aa: str,
    items: list[dict[str, Any]],
    *,
    only_afms: set[str] | None = None,
    log: Any = None,
) -> dict[str, int]:
    scanned = 0
    inserted = 0
    errors = 0
    wanted = {norm_afm(a) for a in only_afms} if only_afms is not None else None
    if wanted is not None:
        wanted.discard("")
    for item in items:
        afm = norm_afm(item.get("afm") or item.get("Afm") or "")
        if not afm:
            continue
        if wanted is not None and afm not in wanted:
            continue
        scanned += 1
        try:
            result = apply_ex_base_05_personal(employer_afm, branch_aa, item) or {}
            if result.get("inserted"):
                inserted += 1
        except Exception as ex:  # noqa: BLE001
            errors += 1
            if log:
                log.error(f"Σύμβαση από EX_BASE_05 {afm}: {ex}")
    return {"scanned": scanned, "inserted": inserted, "errors": errors}


def refresh_personal_from_ex_base_05(
    ctx: dict[str, Any],
    *,
    only_afms: set[str] | list[str] | None = None,
    log: Any = None,
) -> dict[str, Any]:
    """Ημ. πρόσληψης, ΑΜΚΑ, ΑΜΑ και προσωπικά σύμβασης από EX_BASE_05.

    Χρησιμοποιεί web/API credentials (όχι portal admin) και δεν εξαρτάται από
    Flask request/session — ώστε να τρέχει και στο ημερήσιο job των 04:00.
    """
    from app.ergani_env import api_login_credentials, client_for_store
    from app.ergani_parse import extract_raw_list
    from app.http_helpers import json_or_text

    try:
        api_user, api_pwd, api_ut = api_login_credentials(ctx)
    except ValueError:
        return {"success": False, "skipped": True, "detail": "no_api_user"}
    try:
        client = client_for_store(ctx)
        auth = client.authenticate(api_user, api_pwd, api_ut)
        auth_payload = json_or_text(auth)
        if not auth.ok or not isinstance(auth_payload, dict) or not auth_payload.get("accessToken"):
            return {"success": False, "detail": "auth_fail"}
        bearer = str(auth_payload["accessToken"])
        resp = client.execute_service("EX_BASE_05", [], bearer)
        if not resp.ok:
            return {"success": False, "detail": f"HTTP {resp.status_code}"}
        items = extract_raw_list(json_or_text(resp))
        wanted = None
        if only_afms is not None:
            wanted = {norm_afm(a) for a in only_afms}
            wanted.discard("")
        stats = apply_ex_base_05_items(
            str(ctx.get("employer_afm") or ""),
            str(ctx.get("branch_aa") or "0"),
            items,
            only_afms=wanted,
            log=log,
        )
        if log:
            log.info(
                f"Προσωπικά EX_BASE_05: {stats['inserted']} νέες εκδόσεις "
                f"({stats['scanned']} εργαζόμενοι)",
                **stats,
            )
        return {"success": True, **stats}
    except Exception as ex:  # noqa: BLE001
        if log:
            log.error(f"Προσωπικά EX_BASE_05: {ex}")
        return {"success": False, "detail": str(ex)}

