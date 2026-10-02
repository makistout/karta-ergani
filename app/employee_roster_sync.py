"""Ημερήσιο δυναμικό προσωπικού: EX_BASE_01/02/05 και απενεργοποίηση όσων έφυγαν."""

from __future__ import annotations

from typing import Any

from app.db import cursor
from app.ergani_env import api_login_credentials, client_for_store
from app.ergani_parse import extract_raw_list, parse_branches, parse_employees, parse_employer_profile
from app.http_helpers import json_or_text
from app.repo_entities import (
    deactivate_stale_employments,
    upsert_employee,
    upsert_employer,
    upsert_employment,
    upsert_parartima,
)
from app.work_card_payload import norm_afm


def sync_employee_roster_authenticated(
    client: Any,
    bearer: str,
    afm: str,
    aa: str,
    log: Any = None,
) -> dict[str, Any]:
    """Ενημερώνει τρέχοντες και απενεργοποιεί όσους δεν είναι πλέον στο EX_BASE_05."""
    synced = 0
    deactivated = 0
    try:
        r01 = client.execute_service("EX_BASE_01", [], bearer)
        p01 = json_or_text(r01)
        if r01.ok:
            prof = parse_employer_profile(p01)
            with cursor() as cur:
                upsert_employer(cur, afm, eponimia=prof.get("eponimia"))
            if log:
                log.info("Προσωπικό: εργοδότης ενημερώθηκε (EX_BASE_01)")
        elif log:
            log.error(f"Προσωπικό: αποτυχία EX_BASE_01 — HTTP {r01.status_code}")

        r02 = client.execute_service("EX_BASE_02", [], bearer)
        p02 = json_or_text(r02)
        if r02.ok:
            branches = parse_branches(p02)
            with cursor() as cur:
                employer_id = upsert_employer(cur, afm)
                if employer_id:
                    for branch in branches:
                        upsert_parartima(
                            cur,
                            employer_id,
                            branch["aa"],
                            description=branch.get("description"),
                        )
            if log:
                log.info(
                    f"Προσωπικό: παραρτήματα ενημερώθηκαν (EX_BASE_02) — {len(branches)}"
                )
        elif log:
            log.error(f"Προσωπικό: αποτυχία EX_BASE_02 — HTTP {r02.status_code}")

        r05 = client.execute_service("EX_BASE_05", [], bearer)
        p05 = json_or_text(r05)
        if not r05.ok:
            detail = f"HTTP {r05.status_code}"
            if log:
                log.error(f"Προσωπικό: αποτυχία EX_BASE_05 — {detail}")
            return {"success": False, "detail": detail, "count": 0, "deactivated": 0}

        employees = parse_employees(p05)
        active_afms: set[str] = set()
        with cursor() as cur:
            employer_id = upsert_employer(cur, afm)
            if not employer_id:
                raise RuntimeError("Δεν δημιουργήθηκε employer_id")
            part_id = upsert_parartima(cur, employer_id, aa)
            for emp in employees:
                e_afm = emp.get("afm")
                if not e_afm:
                    continue
                active_afms.add(norm_afm(e_afm))
                emp_id = upsert_employee(
                    cur,
                    e_afm,
                    emp.get("eponymo"),
                    emp.get("onoma"),
                    flex_arrival_minutes=emp.get("flex_arrival_minutes"),
                    amka=emp.get("amka"),
                    amika=emp.get("amika"),
                )
                if emp_id:
                    upsert_employment(
                        cur,
                        employer_id,
                        emp_id,
                        part_id,
                        hire_date=emp.get("hire_date"),
                    )
                    synced += 1
            if active_afms:
                deactivated = deactivate_stale_employments(
                    cur, employer_id, active_afms, parartima_id=part_id
                )
        from app.repo_employment_contract import apply_ex_base_05_items

        apply_ex_base_05_items(afm, aa, extract_raw_list(p05), log=log)
        detail = f"{synced} ενεργοί, {deactivated} ανενεργοί"
        if log:
            log.info(f"Προσωπικό: {detail}", count=synced, deactivated=deactivated)
        return {
            "success": True,
            "detail": detail,
            "count": synced,
            "deactivated": deactivated,
        }
    except Exception as ex:
        if log:
            log.error(str(ex))
        return {
            "success": False,
            "detail": str(ex),
            "count": synced,
            "deactivated": deactivated,
        }


def sync_employee_roster(ctx: dict[str, Any], log: Any = None) -> dict[str, Any]:
    """Ίδιο με το κουμπί Συγχρονισμός Ergani για προσωπικό, χωρίς Flask session."""
    try:
        api_user, api_pwd, api_ut = api_login_credentials(ctx)
    except ValueError:
        return {"success": False, "skipped": True, "detail": "no_api_user", "count": 0}
    client = client_for_store(ctx)
    auth = client.authenticate(api_user, api_pwd, api_ut)
    payload = json_or_text(auth)
    if not auth.ok or not isinstance(payload, dict) or not payload.get("accessToken"):
        return {"success": False, "detail": "auth_fail", "count": 0}
    return sync_employee_roster_authenticated(
        client,
        str(payload["accessToken"]),
        str(ctx.get("employer_afm") or "").strip(),
        str(ctx.get("branch_aa") or "0").strip()[:32] or "0",
        log,
    )
