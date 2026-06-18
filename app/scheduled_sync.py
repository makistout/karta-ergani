"""Περιοδικός συγχρονισμός όλων των καταστημάτων — ωράριο + πραγματική για σήμερα."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from app.ergani_env import store_api_context
from app.karta_log import KartaLogger
from app.portal_schedule_sync import sync_schedule_from_portal
from app.portal_work_log_sync import sync_work_log_from_portal
from app import repo_store, repo_sync_log

OPERATION = "scheduled_today_sync"
_RUNNING_GRACE_MINUTES = 15


def is_store_syncable(cfg: dict[str, Any]) -> bool:
    """Κατάστημα με credentials portal (admin) και ΑΦΜ εργοδότη."""
    if not str(cfg.get("employer_afm") or "").strip():
        return False
    if not str(cfg.get("username") or "").strip():
        return False
    if not str(cfg.get("password") or "").strip():
        return False
    return True


def list_syncable_stores() -> list[dict[str, Any]]:
    return [s for s in repo_store.list_store_configs() if is_store_syncable(s)]


def _today_iso() -> str:
    return datetime.today().strftime("%Y-%m-%d")


def _has_running_scheduled_sync() -> bool:
    if not repo_sync_log.tables_available():
        return False
    try:
        from app.db import cursor

        with cursor(commit=False) as cur:
            cur.execute(
                """
                SELECT TOP (1) 1
                FROM dbo.karta_sync_run
                WHERE operation = ?
                  AND LOWER(RTRIM(status)) = N'running'
                  AND started_at >= DATEADD(MINUTE, ?, SYSDATETIMEOFFSET())
                """,
                (OPERATION, -_RUNNING_GRACE_MINUTES),
            )
            return cur.fetchone() is not None
    except Exception:
        return False


def _log_portal_phase(
    log: KartaLogger,
    label: str,
    result: dict[str, Any],
) -> None:
    """Γραμμές καταγραφής για φάση portal (ωράριο / πραγματική)."""
    if result.get("success"):
        src = str(result.get("fetch_source") or result.get("source") or "").strip()
        src_part = f", πηγή {src}" if src else ""
        log.info(
            f"{label}: OK — {result.get('count', 0)} εγγραφές{src_part}",
            count=result.get("count"),
            days_synced=result.get("days_synced"),
            source=src or None,
        )
    else:
        detail = str(result.get("detail") or "αποτυχία").strip()
        log.error(f"{label}: {detail}")
        for err in (result.get("errors") or [])[:5]:
            log.error(f"{label}: {err}")


def _fmt_sync_ts(value: Any) -> str | None:
    if value is None:
        return None
    if hasattr(value, "strftime"):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    s = str(value).strip()
    return s.replace("T", " ")[:19] if s else None


def _log_store_sync_timestamps(
    log: KartaLogger,
    store_id: int,
    *,
    schedule_ok: bool,
    work_log_ok: bool,
) -> dict[str, str | None]:
    """Καταγραφή και επιστροφή τελευταίων timestamps από karta_store_config."""
    cfg = repo_store.get_store_config(store_id)
    if not cfg:
        return {"schedule_last_sync_at": None, "work_log_last_sync_at": None}

    sched_ts = _fmt_sync_ts(cfg.get("schedule_last_sync_at"))
    wl_ts = _fmt_sync_ts(cfg.get("work_log_last_sync_at"))

    if schedule_ok and sched_ts:
        log.info(
            f"Ενημερώθηκε schedule_last_sync_at: {sched_ts}",
            schedule_last_sync_at=sched_ts,
        )
    elif not schedule_ok:
        log.warning("Δεν ενημερώθηκε schedule_last_sync_at (αποτυχία sync ωραρίου)")

    if work_log_ok and wl_ts:
        log.info(
            f"Ενημερώθηκε work_log_last_sync_at: {wl_ts}",
            work_log_last_sync_at=wl_ts,
        )
    elif not work_log_ok:
        log.warning("Δεν ενημερώθηκε work_log_last_sync_at (αποτυχία sync πραγματικής)")

    return {
        "schedule_last_sync_at": sched_ts,
        "work_log_last_sync_at": wl_ts,
    }


def _finish_store_run(
    run_id: str,
    *,
    ok: bool,
    message: str,
    result: dict[str, Any],
) -> None:
    repo_sync_log.finish_run(
        run_id,
        status="done" if ok else "error",
        message=message,
        result=result,
    )


def sync_store_today(
    cfg: dict[str, Any],
    *,
    work_date_iso: str | None = None,
) -> dict[str, Any]:
    """Συγχρονισμός μίας ημέρας (προεπιλογή σήμερα): ωράριο + πραγματική + καταγραφή."""
    ctx = store_api_context(cfg)
    today = (work_date_iso or _today_iso()).strip()[:10]
    sid = int(cfg["id"])
    name = str(cfg.get("name") or sid)
    run_id = str(uuid.uuid4())

    log = KartaLogger(
        OPERATION,
        store_id=sid,
        store_name=name,
        run_id=run_id,
        extra={
            "employer_afm": ctx.get("employer_afm"),
            "branch_aa": ctx.get("branch_aa"),
            "work_date": today,
        },
    )
    log.info(
        f"Έναρξη αυτόματου συγχρονισμού για {today}",
        work_date=today,
    )

    try:
        log.info("Φάση 1/2: ψηφιακό ωράριο (portal)…")
        schedule = sync_schedule_from_portal(
            ctx,
            from_iso=today,
            to_iso=today,
            max_days=1,
            run_id=run_id,
        )
        _log_portal_phase(log, "Ψηφιακό ωράριο", schedule)

        log.info("Φάση 2/2: πραγματική απασχόληση (portal)…")
        work_log = sync_work_log_from_portal(
            ctx,
            from_iso=today,
            to_iso=today,
            max_days=1,
            run_id=run_id,
        )
        _log_portal_phase(log, "Πραγματική απασχόληση", work_log)
    except Exception as ex:
        err = str(ex)
        log.error(f"Σφάλμα αυτόματου συγχρονισμού: {err}")
        result = {
            "store_id": sid,
            "store_name": name,
            "work_date": today,
            "success": False,
            "detail": err,
            "schedule": {"success": False},
            "work_log": {"success": False},
        }
        _finish_store_run(
            run_id,
            ok=False,
            message=f"{name}: {err}",
            result=result,
        )
        return result

    ok = bool(schedule.get("success")) and bool(work_log.get("success"))
    sync_times = _log_store_sync_timestamps(
        log,
        sid,
        schedule_ok=bool(schedule.get("success")),
        work_log_ok=bool(work_log.get("success")),
    )
    detail_parts: list[str] = []
    if schedule.get("success"):
        detail_parts.append(f"ωράριο {schedule.get('count', 0)}")
    else:
        detail_parts.append(f"ωράριο: {schedule.get('detail') or 'αποτυχία'}")
    if work_log.get("success"):
        detail_parts.append(f"πραγματική {work_log.get('count', 0)}")
    else:
        detail_parts.append(f"πραγματική: {work_log.get('detail') or 'αποτυχία'}")

    detail = ", ".join(detail_parts)
    summary = f"{'OK' if ok else 'Αποτυχία'} — {detail}"
    log.info(
        f"Ολοκλήρωση αυτόματου συγχρονισμού: {summary}",
        success=ok,
    )

    result = {
        "store_id": sid,
        "store_name": name,
        "work_date": today,
        "run_id": run_id,
        "success": ok,
        "detail": detail,
        "schedule": schedule,
        "work_log": work_log,
        "schedule_last_sync_at": sync_times.get("schedule_last_sync_at"),
        "work_log_last_sync_at": sync_times.get("work_log_last_sync_at"),
    }
    _finish_store_run(
        run_id,
        ok=ok,
        message=f"{name}: {summary}",
        result=result,
    )
    return result


def _log_batch_skip(reason: str) -> str | None:
    if not repo_sync_log.tables_available():
        return None
    run_id = str(uuid.uuid4())
    log = KartaLogger(OPERATION, run_id=run_id)
    log.info(reason)
    repo_sync_log.finish_run(
        run_id,
        status="done",
        message=reason,
        result={"success": True, "skipped": True, "reason": reason},
    )
    return run_id


def run_scheduled_sync(
    *,
    store_ids: list[int] | None = None,
    work_date_iso: str | None = None,
    dry_run: bool = False,
    skip_if_running: bool = True,
) -> dict[str, Any]:
    """
    Συγχρονισμός όλων των διαθέσιμων καταστημάτων για μία ημέρα.
    Κάθε κατάστημα γράφει ξεχωριστή εγγραφή στις καταγραφές sync.
    """
    repo_sync_log.reconcile_stale_runs()

    if skip_if_running and _has_running_scheduled_sync():
        reason = "Παράλειψη — ήδη τρέχει αυτόματος συγχρονισμός"
        skip_run_id = _log_batch_skip(reason)
        return {
            "success": True,
            "skipped": True,
            "reason": reason,
            "run_id": skip_run_id,
            "stores": [],
        }

    stores = list_syncable_stores()
    if store_ids is not None:
        wanted = {int(x) for x in store_ids}
        stores = [s for s in stores if int(s["id"]) in wanted]

    today = (work_date_iso or _today_iso()).strip()[:10]

    if dry_run:
        names = [f"{s.get('name')} (id={s['id']})" for s in stores]
        return {
            "success": True,
            "dry_run": True,
            "work_date": today,
            "stores": names,
            "count": len(stores),
        }

    batch_run_id: str | None = None
    batch_log: KartaLogger | None = None
    if len(stores) > 1 and repo_sync_log.tables_available():
        batch_run_id = str(uuid.uuid4())
        batch_log = KartaLogger(OPERATION, run_id=batch_run_id)
        batch_log.info(
            f"Έναρξη κύκλου αυτόματου συγχρονισμού — {len(stores)} καταστήματα, {today}",
            work_date=today,
            store_count=len(stores),
        )

    results: list[dict[str, Any]] = []
    for cfg in stores:
        results.append(sync_store_today(cfg, work_date_iso=today))

    ok_count = sum(1 for r in results if r.get("success"))
    fail_count = len(results) - ok_count
    overall_ok = fail_count == 0 and bool(results)
    summary = (
        f"Αυτόματος sync ολοκληρώθηκε — {ok_count}/{len(results)} OK"
        if results
        else "Αυτόματος sync: κανένα διαθέσιμο κατάστημα"
    )
    if fail_count:
        summary += f", {fail_count} αποτυχίες"

    if batch_log and batch_run_id:
        for row in results:
            mark = "OK" if row.get("success") else "FAIL"
            batch_log.info(
                f"[{mark}] {row.get('store_name')}: {row.get('detail')}",
                store_id=row.get("store_id"),
                success=row.get("success"),
            )
        batch_log.info(summary, ok=ok_count, failed=fail_count)
        repo_sync_log.finish_run(
            batch_run_id,
            status="done" if overall_ok else "error",
            message=summary,
            result={
                "success": overall_ok,
                "work_date": today,
                "stores": results,
                "ok_count": ok_count,
                "fail_count": fail_count,
            },
        )

    return {
        "success": overall_ok,
        "skipped": False,
        "work_date": today,
        "run_id": batch_run_id,
        "ok_count": ok_count,
        "fail_count": fail_count,
        "stores": results,
        "message": summary,
    }
