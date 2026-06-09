"""Συγχρονισμός στοιχείων Ergani → τοπική βάση karta_*."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from app.db import cursor
from app.ergani_client import ErganiClient
from app.ergani_parse import (
    parse_branches,
    parse_employees,
    parse_employer_profile,
)
from app.ergani_env import store_api_context
from app.http_helpers import json_or_text
from app.karta_log import KartaLogger
from app.portal_schedule_sync import iter_schedule_sync_events
from app.portal_work_log_sync import iter_work_log_sync_events
from app.repo_entities import (
    deactivate_stale_employments,
    upsert_employee,
    upsert_employer,
    upsert_employment,
    upsert_parartima,
)
from app import repo_store
from app.work_card_payload import norm_afm

STORE_SYNC_STEPS = 5


def _step(ok: bool, detail: str = "", **extra: Any) -> dict[str, Any]:
    out: dict[str, Any] = {"success": ok, "detail": detail}
    out.update(extra)
    return out


def iter_store_sync_events(
    bearer: str,
    employer_afm: str,
    branch_aa: str,
    store_id: int | None = None,
    *,
    api_base_url: str | None = None,
    run_id: str | None = None,
    store_name: str | None = None,
) -> Iterator[dict[str, Any]]:
    """
    Generator events για πλήρη συγχρονισμό καταστήματος — API + portal (σήμερα).
    """
    log = KartaLogger(
        "store_select",
        store_id=store_id,
        store_name=store_name,
        run_id=run_id,
        register_run=run_id is None,
    )
    client = ErganiClient(api_base_url)
    afm = str(employer_afm).strip()
    aa = str(branch_aa or "0").strip()[:32] or "0"
    total = STORE_SYNC_STEPS
    results: dict[str, Any] = {
        "employer": _step(False),
        "branches": _step(False),
        "employees": _step(False),
        "schedule": _step(False),
        "work_log": _step(False),
    }

    log.info("Έναρξη συγχρονισμού καταστήματος", employer_afm=afm, branch_aa=aa)
    yield {
        "event": "progress",
        "message": "Έναρξη συγχρονισμού…",
        "step": 0,
        "total": total,
    }

    # EX_BASE_01 — στοιχεία εργοδότη
    msg = "Ενημέρωση στοιχείων εργοδότη (EX_BASE_01)…"
    log.info(msg)
    yield {"event": "progress", "message": msg, "step": 1, "total": total}
    try:
        r01 = client.execute_service("EX_BASE_01", [], bearer)
        p01 = json_or_text(r01)
        if r01.ok:
            prof = parse_employer_profile(p01)
            eponimia = prof.get("eponimia") or None
            with cursor() as cur:
                upsert_employer(cur, afm, eponimia=eponimia)
            results["employer"] = _step(True, "Εργοδότης ενημερώθηκε", eponimia=eponimia)
            log.info("Εργοδότης ενημερώθηκε", eponimia=eponimia)
        else:
            detail = f"HTTP {r01.status_code}"
            results["employer"] = _step(False, detail)
            log.error(f"Αποτυχία EX_BASE_01: {detail}")
    except Exception as ex:
        results["employer"] = _step(False, str(ex))
        log.error(f"Σφάλμα EX_BASE_01: {ex}")

    # EX_BASE_02 — παραρτήματα
    msg = "Ενημέρωση παραρτημάτων (EX_BASE_02)…"
    log.info(msg)
    yield {"event": "progress", "message": msg, "step": 2, "total": total}
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
            log.info(f"Αποθηκεύτηκαν {n} παραρτήματα", count=n)
        else:
            detail = f"HTTP {r02.status_code}"
            results["branches"] = _step(False, detail)
            log.error(f"Αποτυχία EX_BASE_02: {detail}")
    except Exception as ex:
        results["branches"] = _step(False, str(ex))
        log.error(f"Σφάλμα EX_BASE_02: {ex}")

    # EX_BASE_05 — εργαζόμενοι
    msg = "Ενημέρωση εργαζομένων (EX_BASE_05)…"
    log.info(msg)
    yield {"event": "progress", "message": msg, "step": 3, "total": total}
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
                        cur,
                        e_afm,
                        emp.get("eponymo"),
                        emp.get("onoma"),
                        flex_arrival_minutes=emp.get("flex_arrival_minutes"),
                    )
                    if emp_id:
                        upsert_employment(cur, employer_id, emp_id, part_id)
                        synced += 1
                if active_afms:
                    deactivate_stale_employments(cur, employer_id, active_afms)
            results["employees"] = _step(True, f"{synced} εργαζόμενοι", count=synced)
            log.info(f"Αποθηκεύτηκαν {synced} εργαζόμενοι", count=synced)
        else:
            detail = f"HTTP {r05.status_code}"
            results["employees"] = _step(False, detail)
            log.error(f"Αποτυχία EX_BASE_05: {detail}")
    except Exception as ex:
        results["employees"] = _step(False, str(ex))
        log.error(f"Σφάλμα EX_BASE_05: {ex}")

    sched_ctx = None
    if store_id:
        cfg = repo_store.get_store_config(int(store_id))
        if cfg:
            sched_ctx = store_api_context(cfg)

    # Ψηφιακό ωράριο — portal
    msg = "Ψηφιακό ωράριο (portal Ergani)…"
    log.info(msg)
    yield {"event": "progress", "message": msg, "step": 4, "total": total}
    if sched_ctx:
        sched_result: dict[str, Any] | None = None
        for ev in iter_schedule_sync_events(
            sched_ctx, max_days=1, run_id=log.run_id
        ):
            ev_type = ev.get("event")
            if ev_type == "progress" and ev.get("message"):
                sub = ev["message"]
                yield {
                    "event": "progress",
                    "message": f"Ωράριο: {sub}",
                    "step": 4,
                    "total": total,
                }
            elif ev_type == "day_ok":
                log.info(
                    ev.get("message") or "Ημέρα ωραρίου OK",
                    work_date=ev.get("work_date"),
                    count=ev.get("count"),
                )
            elif ev_type == "day_err":
                log.error(ev.get("message") or "Σφάλμα ωραρίου")
            elif ev_type == "done":
                sched_result = ev.get("sync") or {}
            elif ev_type == "error":
                sched_result = {
                    "success": False,
                    "detail": ev.get("message") or "Αποτυχία portal ωραρίου",
                    "count": 0,
                }
        if sched_result:
            results["schedule"] = _step(
                sched_result.get("success", False),
                sched_result.get("detail", ""),
                count=sched_result.get("count", 0),
                work_date=sched_result.get("work_date"),
            )
        else:
            results["schedule"] = _step(False, "Διακόπηκε ο συγχρονισμός ωραρίου")
            log.error("Διακόπηκε ο συγχρονισμός ωραρίου")
    else:
        detail = "Δεν βρέθηκε κατάστημα για portal ωράριο"
        results["schedule"] = _step(False, detail, count=0)
        log.warning(detail)

    # Πραγματική απασχόληση — portal
    msg = "Πραγματική απασχόληση (portal Ergani)…"
    log.info(msg)
    yield {"event": "progress", "message": msg, "step": 5, "total": total}
    wl_ctx = sched_ctx
    if wl_ctx:
        wl_result: dict[str, Any] | None = None
        for ev in iter_work_log_sync_events(
            wl_ctx, max_days=1, run_id=log.run_id
        ):
            ev_type = ev.get("event")
            if ev_type == "progress" and ev.get("message"):
                sub = ev["message"]
                yield {
                    "event": "progress",
                    "message": f"Πραγματική: {sub}",
                    "step": 5,
                    "total": total,
                }
            elif ev_type == "day_ok":
                log.info(
                    ev.get("message") or "Ημέρα πραγματικής OK",
                    work_date=ev.get("work_date"),
                    count=ev.get("count"),
                )
            elif ev_type == "day_err":
                log.error(ev.get("message") or "Σφάλμα πραγματικής")
            elif ev_type == "done":
                wl_result = ev.get("sync") or {}
            elif ev_type == "error":
                wl_result = {
                    "success": False,
                    "detail": ev.get("message") or "Αποτυχία portal πραγματικής",
                    "count": 0,
                }
        if wl_result:
            results["work_log"] = _step(
                wl_result.get("success", False),
                wl_result.get("detail", ""),
                count=wl_result.get("count", 0),
                work_date=wl_result.get("work_date"),
            )
        else:
            results["work_log"] = _step(False, "Διακόπηκε ο συγχρονισμός πραγματικής")
            log.error("Διακόπηκε ο συγχρονισμός πραγματικής")
    else:
        detail = "Δεν βρέθηκε κατάστημα για portal πραγματικής απασχόλησης"
        results["work_log"] = _step(False, detail, count=0)
        log.warning(detail)

    if store_id:
        try:
            repo_store.touch_last_sync(int(store_id))
            log.info("Ενημερώθηκε ημερομηνία τελευταίου συγχρονισμού")
        except Exception as ex:
            log.warning(f"Δεν ενημερώθηκε last_sync_at: {ex}")

    ok_all = results["employees"].get("success")
    sync_payload = {"success": bool(ok_all), "sync_results": results}
    summary_parts = []
    if results["employees"].get("success"):
        summary_parts.append(f"{results['employees'].get('count', 0)} εργαζόμενοι")
    if results["schedule"].get("success"):
        summary_parts.append(f"{results['schedule'].get('count', 0)} ωράριο")
    if results["work_log"].get("success"):
        summary_parts.append(f"{results['work_log'].get('count', 0)} πραγματική")
    summary = "Ολοκληρώθηκε — " + ", ".join(summary_parts) if summary_parts else (
        "Ολοκληρώθηκε με προειδοποιήσεις" if ok_all else "Αποτυχία συγχρονισμού"
    )
    log.info(summary, success=bool(ok_all))
    yield {
        "event": "done",
        "success": bool(ok_all),
        "sync": sync_payload,
        "message": summary,
        "logs": log.tail(100),
        "error": None if ok_all else results["employees"].get("detail"),
    }


def sync_store_from_ergani(
    bearer: str,
    employer_afm: str,
    branch_aa: str,
    store_id: int | None = None,
    *,
    api_base_url: str | None = None,
) -> dict[str, Any]:
    """Συγχρονισμός χωρίς streaming — για συμβατότητα."""
    for ev in iter_store_sync_events(
        bearer,
        employer_afm,
        branch_aa,
        store_id,
        api_base_url=api_base_url,
    ):
        if ev.get("event") == "done":
            return ev.get("sync") or {"success": False, "sync_results": {}}
        if ev.get("event") == "error":
            return {"success": False, "sync_results": {}, "detail": ev.get("message")}
    return {"success": False, "sync_results": {}}
