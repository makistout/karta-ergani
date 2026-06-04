"""Συγχρονισμός στοιχείων Ergani → τοπική βάση karta_*."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app.db import cursor
from app.ergani_client import ErganiClient
from app.date_util import format_date_for_ergani
from app.ergani_parse import (
    parse_branches,
    parse_employees,
    parse_employer_profile,
)
from app.ergani_env import store_api_context
from app.schedule_sync import fetch_and_save_schedule_for_ctx
from app.work_log_sync import fetch_and_save_work_log_for_ctx
from app.http_helpers import json_or_text
from app.repo_entities import (
    deactivate_stale_employments,
    upsert_employee,
    upsert_employer,
    upsert_employment,
    upsert_parartima,
)
from app import repo_store
from app.work_card_payload import norm_afm


def _step(ok: bool, detail: str = "", **extra: Any) -> dict[str, Any]:
    out: dict[str, Any] = {"success": ok, "detail": detail}
    out.update(extra)
    return out


def sync_store_from_ergani(
    bearer: str,
    employer_afm: str,
    branch_aa: str,
    store_id: int | None = None,
    *,
    api_base_url: str | None = None,
) -> dict[str, Any]:
    """
    Αντλεί από Ergani: εργοδότη, παραρτήματα, εργαζόμενους.
    Ψηφιακό ωράριο: portal (σήμερα). Work log: κλήση API χωρίς αποθήκευση ακόμα.
    """
    client = ErganiClient(api_base_url)
    afm = str(employer_afm).strip()
    aa = str(branch_aa or "0").strip()[:32] or "0"
    results: dict[str, Any] = {
        "employer": _step(False),
        "branches": _step(False),
        "employees": _step(False),
        "schedule": _step(False),
        "work_log": _step(False),
    }

    # EX_BASE_01 — στοιχεία εργοδότη
    try:
        r01 = client.execute_service("EX_BASE_01", [], bearer)
        p01 = json_or_text(r01)
        if r01.ok:
            prof = parse_employer_profile(p01)
            eponimia = prof.get("eponimia") or None
            with cursor() as cur:
                upsert_employer(cur, afm, eponimia=eponimia)
            results["employer"] = _step(True, "Εργοδότης ενημερώθηκε", eponimia=eponimia)
        else:
            results["employer"] = _step(False, f"HTTP {r01.status_code}")
    except Exception as ex:
        results["employer"] = _step(False, str(ex))

    # EX_BASE_02 — παραρτήματα
    try:
        r02 = client.execute_service("EX_BASE_02", [], bearer)
        p02 = json_or_text(r02)
        if r02.ok:
            branches = parse_branches(p02)
            n = 0
            with cursor() as cur:
                employer_id = upsert_employer(cur, afm)
                if employer_id:
                    for b in branches:
                        upsert_parartima(
                            cur,
                            employer_id,
                            b["aa"],
                            description=b.get("description"),
                        )
                        n += 1
            results["branches"] = _step(True, f"{n} παραρτήματα", count=n)
        else:
            results["branches"] = _step(False, f"HTTP {r02.status_code}")
    except Exception as ex:
        results["branches"] = _step(False, str(ex))

    # EX_BASE_05 — εργαζόμενοι
    try:
        r05 = client.execute_service("EX_BASE_05", [], bearer)
        p05 = json_or_text(r05)
        if r05.ok:
            employees = parse_employees(p05)
            active_afms: set[str] = set()
            synced = 0
            with cursor() as cur:
                employer_id = upsert_employer(cur, afm)
                if not employer_id:
                    raise RuntimeError("Δεν δημιουργήθηκε employer_id")
                part_id = upsert_parartima(cur, employer_id, aa)
                for emp in employees:
                    e_afm = emp["afm"]
                    if not e_afm:
                        continue
                    active_afms.add(norm_afm(e_afm))
                    emp_id = upsert_employee(
                        cur, e_afm, emp.get("eponymo"), emp.get("onoma")
                    )
                    if emp_id:
                        upsert_employment(cur, employer_id, emp_id, part_id)
                        synced += 1
                if active_afms:
                    deactivate_stale_employments(cur, employer_id, active_afms)
            results["employees"] = _step(
                True, f"{synced} εργαζόμενοι", count=synced
            )
        else:
            results["employees"] = _step(False, f"HTTP {r05.status_code}")
    except Exception as ex:
        results["employees"] = _step(False, str(ex))

    try:
        sched_ctx = None
        if store_id:
            cfg = repo_store.get_store_config(int(store_id))
            if cfg:
                sched_ctx = store_api_context(cfg)
        if sched_ctx:
            sched = fetch_and_save_schedule_for_ctx(sched_ctx, None, None, max_days=1)
        else:
            sched = {"success": False, "detail": "Δεν βρέθηκε κατάστημα για portal ωράριο", "count": 0}
        results["schedule"] = _step(
            sched.get("success", False),
            sched.get("detail", ""),
            count=sched.get("count", 0),
            work_date=sched.get("work_date"),
        )
    except Exception as ex:
        results["schedule"] = _step(False, str(ex))

    try:
        wl_ctx = None
        if store_id:
            cfg = repo_store.get_store_config(int(store_id))
            if cfg:
                wl_ctx = store_api_context(cfg)
        if wl_ctx:
            wl = fetch_and_save_work_log_for_ctx(wl_ctx, None, None, max_days=1)
        else:
            wl = {
                "success": False,
                "detail": "Δεν βρέθηκε κατάστημα για portal πραγματικής απασχόλησης",
                "count": 0,
            }
        results["work_log"] = _step(
            wl.get("success", False),
            wl.get("detail", ""),
            count=wl.get("count", 0),
            work_date=wl.get("work_date"),
        )
    except Exception as ex:
        results["work_log"] = _step(False, str(ex))

    if store_id:
        try:
            repo_store.touch_last_sync(int(store_id))
        except Exception:
            pass

    ok_all = results["employees"].get("success")
    return {"success": bool(ok_all), "sync_results": results}
