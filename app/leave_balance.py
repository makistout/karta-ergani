"""Έλεγχος υπολοίπου κανονικής άδειας πριν από νέα δήλωση."""

from __future__ import annotations

import json
from calendar import monthrange
from datetime import date, datetime
from typing import Any

from app.leave_types import LEAVE_TYPES
from app.repo_employee_leave import (
    load_current_year_normal_leave,
    load_schedule_archive_latest_month,
)
from app.repo_employment_contract import list_current_for_store
from app.work_card_payload import norm_afm

NORMAL_LEAVE_CODE = "ADKAN"
NORMAL_LEAVE_LABEL = next(
    (item["label"] for item in LEAVE_TYPES if item["code"] == NORMAL_LEAVE_CODE),
    "Κανονική άδεια",
)


def is_normal_leave_type(value: str | None) -> bool:
    raw = str(value or "").strip()
    if not raw:
        return False
    if raw.upper() == NORMAL_LEAVE_CODE:
        return True
    folded = raw.casefold()
    return "κανονικ" in folded.replace("ή", "η")


def annual_normal_leave_entitlement(contract: dict[str, Any] | None) -> int | None:
    if not contract:
        return None
    days_raw = str(contract.get("weekly_work_days") or "")
    if "6" in days_raw:
        return 26
    if "5" in days_raw:
        return 22
    return None


def normal_leave_block_message(*, employee_name: str, days_taken: int, days_entitled: int) -> str:
    name = str(employee_name or "").strip() or "εργαζόμενος"
    return (
        f"Ο εργαζόμενος {name} έχει ήδη {days_taken}/{days_entitled} μέρες "
        f"κανονικής άδειας και δεν μπορεί να προστεθεί άλλη μέρα"
    )


def _as_of_for_year(year: int, today: date | None = None) -> date:
    as_today = today or date.today()
    if year < as_today.year:
        return date(year, 12, 31)
    if year > as_today.year:
        return date(year, 1, 1)
    return as_today


def _parse_leave_date(value: Any) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(text[:10], fmt).date()
        except ValueError:
            continue
    return None


def _iter_blocks(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        return [value]
    return []


def _count_submitted_normal_leave_days(
    *,
    employer_afm: str,
    employee_afm: str,
    year: int,
    after: date | None,
) -> int:
    from app.db import cursor

    afm = norm_afm(employee_afm)
    if not afm:
        return 0
    sql = """
        SELECT request_json
        FROM dbo.karta_declaration
        WHERE submission_code = N'WTOLeave'
          AND success = 1
          AND employer_afm = ?
          AND request_json LIKE ?
    """
    try:
        with cursor(commit=False) as cur:
            cur.execute(sql, [norm_afm(employer_afm), f"%{afm}%"])
            rows = cur.fetchall()
    except Exception:
        return 0
    seen: set[date] = set()
    for row in rows:
        try:
            payload = json.loads(row[0] or "{}")
        except (TypeError, ValueError, json.JSONDecodeError):
            continue
        wtos = payload.get("WTOS") if isinstance(payload, dict) else None
        wto_list = _iter_blocks((wtos or {}).get("WTO") if isinstance(wtos, dict) else None)
        for block in wto_list:
            employees = _iter_blocks(((block or {}).get("Ergazomenoi") or {}).get("ErgazomenoiWTO"))
            for emp in employees:
                if not isinstance(emp, dict):
                    continue
                if norm_afm(str(emp.get("f_afm") or "")) != afm:
                    continue
                work_date = _parse_leave_date(emp.get("f_date"))
                if work_date is None or work_date.year != year:
                    continue
                if after is not None and work_date <= after:
                    continue
                analytics = _iter_blocks(
                    ((emp.get("ErgazomenosAnalytics") or {}).get("ErgazomenosWTOAnalytics"))
                )
                if any(str((item or {}).get("f_type") or "").upper() == NORMAL_LEAVE_CODE for item in analytics):
                    seen.add(work_date)
    return len(seen)


def normal_leave_used_days(
    *,
    store_id: int,
    employer_afm: str,
    employee_afm: str,
    year: int,
    today: date | None = None,
) -> int:
    as_of = _as_of_for_year(year, today)
    taken = 0
    try:
        leave_map = load_current_year_normal_leave(
            store_id=int(store_id),
            employee_afms=[employee_afm],
            today=as_of,
        )
    except Exception:
        leave_map = {}
    row = leave_map.get(norm_afm(employee_afm)) or leave_map.get(str(employee_afm or "").strip())
    if row and row.get("days_taken") is not None:
        taken = int(row["days_taken"] or 0)
    after = None
    try:
        latest = load_schedule_archive_latest_month(store_id=int(store_id))
    except Exception:
        latest = None
    if latest and latest.year == year:
        after = date(latest.year, latest.month, monthrange(latest.year, latest.month)[1])
    if after is not None:
        taken += _count_submitted_normal_leave_days(
            employer_afm=employer_afm,
            employee_afm=employee_afm,
            year=year,
            after=after,
        )
    return taken


def normal_leave_block_reason(
    *,
    store_id: int,
    employer_afm: str,
    branch_aa: str,
    employee_afm: str,
    employee_name: str,
    leave_type: str,
    leave_date: date | str | None = None,
    extra_pending_days: int = 0,
    today: date | None = None,
) -> str | None:
    if not is_normal_leave_type(leave_type):
        return None
    afm = norm_afm(employee_afm)
    if not afm:
        return None
    work_date = leave_date if isinstance(leave_date, date) else _parse_leave_date(leave_date)
    as_today = today or date.today()
    year = work_date.year if work_date else as_today.year
    try:
        contract = next(
            (
                item for item in list_current_for_store(employer_afm, str(branch_aa or "0"))
                if norm_afm(str(item.get("employee_afm") or "")) == afm
            ),
            None,
        )
    except Exception:
        contract = None
    entitled = annual_normal_leave_entitlement(contract)
    if entitled is None:
        return None
    taken = normal_leave_used_days(
        store_id=int(store_id),
        employer_afm=employer_afm,
        employee_afm=afm,
        year=year,
        today=as_today,
    ) + max(0, int(extra_pending_days or 0))
    if taken >= entitled:
        return normal_leave_block_message(
            employee_name=employee_name, days_taken=taken, days_entitled=entitled,
        )
    return None
