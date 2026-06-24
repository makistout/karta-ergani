"""Συγχρονισμός περιόδου — εργαζόμενοι (API) + portal ωράριο + πραγματική."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime
from typing import Any

from app.db import cursor
from app.ergani_client import ErganiClient
from app.ergani_parse import parse_branches, parse_employees, parse_employer_profile
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
from app.work_card_payload import norm_afm

PERIOD_SYNC_PHASES = 3


def _sync_employees_api(
    client: ErganiClient,
    bearer: str,
    afm: str,
    aa: str,
    log: KartaLogger,
) -> dict[str, Any]:
    synced = 0
    try:
        r01 = client.execute_service("EX_BASE_01", [], bearer)
        p01 = json_or_text(r01)
        if r01.ok:
            prof = parse_employer_profile(p01)
            with cursor() as cur:
                upsert_employer(cur, afm, eponimia=prof.get("eponimia"))
            log.info("Προσωπικό: εργοδότης ενημερώθηκε (EX_BASE_01)")
        else:
            log.error(f"Προσωπικό: αποτυχία EX_BASE_01 — HTTP {r01.status_code}")

        r02 = client.execute_service("EX_BASE_02", [], bearer)
        p02 = json_or_text(r02)
        if r02.ok:
            branches = parse_branches(p02)
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
            log.info(f"Προσωπικό: παραρτήματα ενημερώθηκαν (EX_BASE_02) — {len(branches)}")
        else:
            log.error(f"Προσωπικό: αποτυχία EX_BASE_02 — HTTP {r02.status_code}")

        r05 = client.execute_service("EX_BASE_05", [], bearer)
        p05 = json_or_text(r05)
        if not r05.ok:
            detail = f"HTTP {r05.status_code}"
            log.error(f"Προσωπικό: αποτυχία EX_BASE_05 — {detail}")
            return {"success": False, "detail": detail, "count": 0}

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
                )
                if emp_id:
                    upsert_employment(cur, employer_id, emp_id, part_id)
                    synced += 1
            if active_afms:
                deactivate_stale_employments(
                    cur, employer_id, active_afms, parartima_id=part_id
                )
        log.info(f"Προσωπικό: αποθηκεύτηκαν {synced} εργαζόμενοι (EX_BASE_05)", count=synced)
        return {"success": True, "detail": f"{synced} εργαζόμενοι", "count": synced}
    except Exception as ex:
        log.error(str(ex))
        return {"success": False, "detail": str(ex), "count": synced}


def _forward_portal(
    events: Iterator[dict[str, Any]],
    prefix: str,
    log: KartaLogger,
) -> Iterator[dict[str, Any]]:
    for ev in events:
        kind = ev.get("event")
        if kind == "progress" and ev.get("message"):
            yield {**ev, "message": f"{prefix}: {ev['message']}"}
        elif kind == "range_ok":
            log.info(
                ev.get("message") or f"{prefix} OK",
                count=ev.get("count"),
                source=ev.get("source"),
            )
            yield ev
        elif kind == "day_ok":
            log.info(
                ev.get("message") or f"{prefix} OK",
                work_date=ev.get("work_date"),
                count=ev.get("count"),
            )
            yield ev
        elif kind == "day_err":
            log.error(ev.get("message") or f"{prefix} σφάλμα")
            yield ev
        elif kind == "done":
            yield ev
            return
        elif kind == "error":
            yield ev
            return
        else:
            yield ev


def iter_period_sync_events(
    ctx: dict[str, Any],
    bearer: str,
    from_iso: str,
    to_iso: str,
    *,
    run_id: str | None = None,
    max_days: int = 31,
) -> Iterator[dict[str, Any]]:
    log = KartaLogger(
        "period_sync",
        store_id=ctx.get("id"),
        store_name=ctx.get("name"),
        run_id=run_id,
        register_run=run_id is None,
    )
    client = ErganiClient(ctx.get("api_base_url"))
    afm = str(ctx["employer_afm"]).strip()
    aa = str(ctx.get("branch_aa") or "0").strip()[:32] or "0"
    results: dict[str, Any] = {
        "employees": {"success": False},
        "schedule": {"success": False},
        "work_log": {"success": False},
    }

    log.info(
        "Έναρξη συγχρονισμού περιόδου",
        from_iso=from_iso,
        to_iso=to_iso,
        employer_afm=afm,
    )
    yield {
        "event": "progress",
        "message": f"Έναρξη συγχρονισμού ({from_iso} – {to_iso})…",
        "step": 0,
        "total": PERIOD_SYNC_PHASES,
    }

    msg = "Προσωπικό (Ergani API EX_BASE_01/02/05)…"
    log.info(msg)
    yield {"event": "progress", "message": msg, "step": 1, "total": PERIOD_SYNC_PHASES}
    emp = _sync_employees_api(client, bearer, afm, aa, log)
    results["employees"] = emp

    msg = "Ψηφιακό ωράριο (portal Ergani)…"
    log.info(msg)
    yield {"event": "progress", "message": msg, "step": 2, "total": PERIOD_SYNC_PHASES}
    sched_result: dict[str, Any] | None = None
    for ev in _forward_portal(
        iter_schedule_sync_events(
            ctx,
            from_iso=from_iso,
            to_iso=to_iso,
            max_days=max_days,
            run_id=run_id,
        ),
        "Ψηφιακό ωράριο",
        log,
    ):
        kind = ev.get("event")
        if kind == "progress":
            yield {**ev, "step": 2, "total": PERIOD_SYNC_PHASES}
        elif kind == "done":
            sched_result = ev.get("sync") or {}
            break
        elif kind == "error":
            sched_result = {
                "success": False,
                "detail": ev.get("message") or "Αποτυχία ωραρίου",
            }
            break
    if sched_result:
        results["schedule"] = sched_result
    else:
        results["schedule"] = {"success": False, "detail": "Διακόπηκε ο συγχρονισμός ωραρίου"}

    msg = "Πραγματική απασχόληση (portal Ergani)…"
    log.info(msg)
    yield {"event": "progress", "message": msg, "step": 3, "total": PERIOD_SYNC_PHASES}
    wl_result: dict[str, Any] | None = None
    for ev in _forward_portal(
        iter_work_log_sync_events(
            ctx,
            from_iso=from_iso,
            to_iso=to_iso,
            max_days=max_days,
            run_id=run_id,
        ),
        "Πραγματική απασχόληση",
        log,
    ):
        kind = ev.get("event")
        if kind == "progress":
            yield {**ev, "step": 3, "total": PERIOD_SYNC_PHASES}
        elif kind == "done":
            wl_result = ev.get("sync") or {}
            break
        elif kind == "error":
            wl_result = {
                "success": False,
                "detail": ev.get("message") or "Αποτυχία πραγματικής",
            }
            break
    if wl_result:
        results["work_log"] = wl_result
    else:
        results["work_log"] = {
            "success": False,
            "detail": "Διακόπηκε ο συγχρονισμός πραγματικής",
        }

    ok = (
        results["employees"].get("success")
        and results["schedule"].get("success")
        and results["work_log"].get("success")
    )
    post_sync_notifications_enqueued = False
    today_iso = datetime.today().strftime("%Y-%m-%d")
    if ok and from_iso <= today_iso <= to_iso:
        from app import repo_store
        from app.scheduled_sync import enqueue_post_sync_notifications

        cfg = repo_store.get_store_config(int(ctx["id"]))
        if cfg:
            post_sync_notifications_enqueued = enqueue_post_sync_notifications(
                cfg,
                work_date_iso=today_iso,
                parent_run_id=run_id,
            )
            if post_sync_notifications_enqueued:
                log.info(
                    "Έγινε enqueue ασύγχρονων ειδοποιήσεων μετά το sync περιόδου",
                    work_date=today_iso,
                )
    parts = []
    if results["employees"].get("success"):
        parts.append(f"{results['employees'].get('count', 0)} εργαζόμενοι")
    if results["schedule"].get("success"):
        parts.append(
            f"{results['schedule'].get('count', 0)} ωράριο "
            f"({results['schedule'].get('days_synced', 0)} ημέρες)"
        )
    if results["work_log"].get("success"):
        parts.append(
            f"{results['work_log'].get('count', 0)} πραγματική "
            f"({results['work_log'].get('days_synced', 0)} ημέρες)"
        )
    summary = (
        "Ολοκληρώθηκε — " + ", ".join(parts)
        if parts
        else "Ολοκληρώθηκε με σφάλματα"
    )
    log.info(summary, success=ok)
    yield {
        "event": "done",
        "success": ok,
        "sync": {
            "success": ok,
            "sync_results": results,
            "post_sync_notifications_enqueued": post_sync_notifications_enqueued,
        },
        "message": summary,
        "logs": log.tail(200),
        "error": None if ok else summary,
    }
