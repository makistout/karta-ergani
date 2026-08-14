"""Περιοδικός συγχρονισμός όλων των καταστημάτων — ωράριο + πραγματική."""

from __future__ import annotations

import threading
import time
import uuid
from datetime import datetime, timedelta
from typing import Any

from app.ergani_env import store_api_context
from app.karta_log import KartaLogger
from app.portal_schedule_sync import sync_schedule_from_portal
from app.portal_work_log_sync import sync_work_log_from_portal
from app.portal_card_protocol_sync import sync_card_protocols_from_portal
from app.work_card_payload import tz_athens
from app import repo_store, repo_sync_log
from app.scheduled_sync_notifications import (
    _post_sync_notify_key,
    enqueue_post_sync_notifications,
)
from config import Config

OPERATION = "scheduled_today_sync"
OPERATION_FUTURE_SCHEDULE_SYNC = "scheduled_future_schedule_sync"
OPERATION_NIGHTLY_RECENT_WORK_LOG_SYNC = "scheduled_recent_work_log_sync"
OPERATION_NIGHTLY_PROTOCOL_SYNC = "scheduled_nightly_protocol_sync"
OPERATION_WEEKLY_REPAIR_WORK_LOG_SYNC = "scheduled_weekly_repair_work_log_sync"
OPERATION_EMPLOYMENT_CONTRACT_SYNC = "scheduled_employment_contract_sync"
OPERATION_APOLOGISTIC_SNAPSHOT = "scheduled_apologistic_snapshot"
FUTURE_SCHEDULE_LOOKAHEAD_DAYS = 2
_RUNNING_GRACE_MINUTES = 15
AFTER_LOGIN_SYNC_COOLDOWN_SECONDS = 15 * 60
_after_login_sync_lock = threading.Lock()
_after_login_sync_seen: dict[str, float] = {}


def _enqueue_auto_close_prev_day_action(
    cfg: dict[str, Any],
    *,
    work_date_iso: str,
    parent_run_id: str,
) -> dict[str, Any]:
    from app.auto_close_cards import run_auto_close_prev_day_for_store

    sid = int(cfg["id"])
    result_holder: dict[str, Any] = {}

    def _run() -> None:
        try:
            # Ξαναδιάβασμα ρυθμίσεων: αν απενεργοποιήθηκε μετά το enqueue, μην τρέξεις.
            live = repo_store.get_action_settings(sid)
            if not bool(live.get("auto_close_prev_day_enabled")):
                result_holder["result"] = {
                    "success": True,
                    "skipped": True,
                    "reason": "ρύθμιση ανενεργή πριν την εκτέλεση",
                    "work_date": work_date_iso,
                    "submitted": 0,
                    "failed": 0,
                }
                return
            live_cfg = {**cfg, **live}
            result = run_auto_close_prev_day_for_store(
                live_cfg,
                work_date_iso=work_date_iso,
                parent_run_id=parent_run_id,
            )
            if result.get("success"):
                repo_store.mark_auto_close_prev_day_run(sid, work_date_iso)
            result_holder["result"] = result
        except Exception as ex:
            result_holder["result"] = {
                "success": False,
                "work_date": work_date_iso,
                "submitted": 0,
                "failed": 0,
                "error": str(ex),
            }

    thread = threading.Thread(
        target=_run,
        daemon=False,
        name=f"auto-close-prev-day-{sid}",
    )
    thread.start()
    return {
        "thread": thread,
        "store_id": sid,
        "work_date": work_date_iso,
        "holder": result_holder,
    }


def _run_configured_auto_actions(
    cfg: dict[str, Any],
    *,
    parent_run_id: str,
    enqueue_auto_close: bool = False,
) -> dict[str, Any] | None:
    from app.auto_close_cards import (
        run_auto_close_prev_day_for_store,
        should_run_auto_close_prev_day,
    )

    actions: dict[str, Any] = {}

    future_should_run, future_from, future_to, future_reason = (
        should_run_future_schedule_sync(cfg)
    )
    if future_should_run:
        actions["future_schedule"] = run_future_schedule_sync_for_store(
            cfg,
            from_iso=future_from,
            to_iso=future_to,
        )
    else:
        actions["future_schedule"] = {
            "skipped": True,
            "reason": future_reason,
            "from_iso": future_from or None,
            "to_iso": future_to or None,
        }

    recent_should_run, recent_from, recent_to, recent_reason = (
        should_run_recent_work_log_sync(cfg)
    )
    if recent_should_run:
        actions["recent_work_log"] = run_work_log_range_sync_for_store(
            cfg,
            from_iso=recent_from,
            to_iso=recent_to,
            operation=OPERATION_NIGHTLY_RECENT_WORK_LOG_SYNC,
        )
    else:
        actions["recent_work_log"] = {
            "skipped": True,
            "reason": recent_reason,
            "from_iso": recent_from or None,
            "to_iso": recent_to or None,
        }

    proto_should_run, proto_target, _proto_from, proto_to, proto_reason = (
        should_run_nightly_protocol_sync(cfg)
    )
    if proto_should_run:
        actions["nightly_protocol"] = run_nightly_protocol_sync_for_store(
            cfg,
            target_date_iso=proto_target,
            protocol_to_iso=proto_to,
        )
    else:
        actions["nightly_protocol"] = {
            "skipped": True,
            "reason": proto_reason,
            "target_date": proto_target or None,
            "protocol_to": proto_to or None,
        }

    apologistic_should_run, apologistic_reason = should_run_apologistic_snapshot(cfg)
    if apologistic_should_run:
        from app.apologistic import previous_week
        from app.apologistic_snapshot import generate_store_week

        week_from, week_to = previous_week()
        actions["apologistic_snapshot"] = generate_store_week(cfg, week_from, week_to)
    else:
        actions["apologistic_snapshot"] = {"skipped": True, "reason": apologistic_reason}

    weekly_should_run, weekly_from, weekly_to, weekly_reason = (
        should_run_weekly_repair_work_log_sync(cfg)
    )
    if weekly_should_run:
        actions["weekly_repair_work_log"] = run_work_log_range_sync_for_store(
            cfg,
            from_iso=weekly_from,
            to_iso=weekly_to,
            operation=OPERATION_WEEKLY_REPAIR_WORK_LOG_SYNC,
        )
    else:
        actions["weekly_repair_work_log"] = {
            "skipped": True,
            "reason": weekly_reason,
            "from_iso": weekly_from or None,
            "to_iso": weekly_to or None,
        }

    contract_should_run, contract_reason = should_run_employment_contract_sync(cfg)
    if contract_should_run:
        actions["employment_contract"] = run_employment_contract_sync_for_store(cfg)
    else:
        actions["employment_contract"] = {
            "skipped": True,
            "reason": contract_reason,
        }

    should_run, previous_day, reason = should_run_auto_close_prev_day(cfg)
    if not should_run:
        actions["auto_close_prev_day"] = {
            "enabled": bool(cfg.get("auto_close_prev_day_enabled")),
            "skipped": True,
            "reason": reason,
            "work_date": previous_day or None,
        }
        return actions
    if enqueue_auto_close:
        actions["auto_close_prev_day"] = {
            "queued": True,
            "work_date": previous_day,
            "reason": "θα εκτελεστεί ασύγχρονα ανά κατάστημα",
        }
        actions["_auto_close_job"] = _enqueue_auto_close_prev_day_action(
            cfg,
            work_date_iso=previous_day,
            parent_run_id=parent_run_id,
        )
        return actions
    result = run_auto_close_prev_day_for_store(
        cfg,
        work_date_iso=previous_day,
        parent_run_id=parent_run_id,
    )
    if result.get("success"):
        repo_store.mark_auto_close_prev_day_run(int(cfg["id"]), previous_day)
    actions["auto_close_prev_day"] = result
    return actions


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


def _add_iso_days(date_iso: str, days: int) -> str:
    base = datetime.strptime(date_iso[:10], "%Y-%m-%d").date()
    return (base + timedelta(days=days)).isoformat()


def _operation_run_exists(operation: str, store_id: int, base_date_iso: str) -> bool:
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
                  AND store_id = ?
                  AND LOWER(RTRIM(status)) IN (N'running', N'done')
                  AND CONVERT(date, started_at) = CONVERT(date, ?)
                """,
                (operation, int(store_id), base_date_iso),
            )
            return cur.fetchone() is not None
    except Exception:
        return False


def _normalized_sync_time(raw: str, *, default: str) -> str:
    try:
        from app.auto_close_cards import normalize_auto_close_time

        return normalize_auto_close_time(str(raw or default))
    except Exception:
        return default


def should_run_future_schedule_sync(
    cfg: dict[str, Any],
    *,
    now: datetime | None = None,
) -> tuple[bool, str, str, str]:
    local_now = (now or datetime.now(tz_athens())).astimezone(tz_athens())
    base_date = local_now.date().isoformat()
    from_iso = _add_iso_days(base_date, 1)
    to_iso = _add_iso_days(base_date, FUTURE_SCHEDULE_LOOKAHEAD_DAYS)
    run_time = _normalized_sync_time(
        str(cfg.get("auto_close_prev_day_time") or "00:30"),
        default="00:30",
    )
    if local_now.strftime("%H:%M") < run_time:
        return False, from_iso, to_iso, f"αναμονή μέχρι {run_time}"
    if not repo_sync_log.tables_available():
        return False, from_iso, to_iso, "λείπουν πίνακες sync log για ημερήσιο guard"
    if _operation_run_exists(OPERATION_FUTURE_SCHEDULE_SYNC, int(cfg["id"]), base_date):
        return False, from_iso, to_iso, "έχει ήδη εκτελεστεί σήμερα"
    return True, from_iso, to_iso, "έτοιμο"


def should_run_recent_work_log_sync(
    cfg: dict[str, Any],
    *,
    now: datetime | None = None,
) -> tuple[bool, str, str, str]:
    local_now = (now or datetime.now(tz_athens())).astimezone(tz_athens())
    if not Config.KARTA_SCHEDULED_RECENT_WORK_LOG_ENABLED:
        return False, "", "", "απενεργοποιημένο από ρύθμιση"
    days = max(1, int(Config.KARTA_SCHEDULED_RECENT_WORK_LOG_DAYS or 30))
    base_date = local_now.date().isoformat()
    from_iso = _add_iso_days(base_date, -(days - 1))
    to_iso = base_date
    run_time = _normalized_sync_time(
        Config.KARTA_SCHEDULED_RECENT_WORK_LOG_TIME,
        default="03:00",
    )
    if local_now.strftime("%H:%M") < run_time:
        return False, from_iso, to_iso, f"αναμονή μέχρι {run_time}"
    if not repo_sync_log.tables_available():
        return False, from_iso, to_iso, "λείπουν πίνακες sync log για ημερήσιο guard"
    if _operation_run_exists(
        OPERATION_NIGHTLY_RECENT_WORK_LOG_SYNC,
        int(cfg["id"]),
        base_date,
    ):
        return False, from_iso, to_iso, "έχει ήδη εκτελεστεί σήμερα"
    return True, from_iso, to_iso, "έτοιμο"


def should_run_nightly_protocol_sync(
    cfg: dict[str, Any],
    *,
    now: datetime | None = None,
) -> tuple[bool, str, str, str, str]:
    """Νυχτερινό sync πρωτοκόλλων + 1-1 απαγωγή για την προηγούμενη ημέρα (~03:00)."""
    local_now = (now or datetime.now(tz_athens())).astimezone(tz_athens())
    if not Config.KARTA_SCHEDULED_PROTOCOL_SYNC_ENABLED:
        return False, "", "", "", "απενεργοποιημένο από ρύθμιση"
    base_date = local_now.date().isoformat()
    target_date = _add_iso_days(base_date, -1)
    run_time = _normalized_sync_time(
        Config.KARTA_SCHEDULED_PROTOCOL_SYNC_TIME,
        default="03:00",
    )
    if local_now.strftime("%H:%M") < run_time:
        return False, target_date, target_date, base_date, f"αναμονή μέχρι {run_time}"
    if not repo_sync_log.tables_available():
        return False, target_date, target_date, base_date, "λείπουν πίνακες sync log"
    if _operation_run_exists(
        OPERATION_NIGHTLY_PROTOCOL_SYNC,
        int(cfg["id"]),
        base_date,
    ):
        return False, target_date, target_date, base_date, "έχει ήδη εκτελεστεί σήμερα"
    return True, target_date, target_date, base_date, "έτοιμο"


def run_nightly_protocol_sync_for_store(
    cfg: dict[str, Any],
    *,
    target_date_iso: str,
    protocol_to_iso: str,
) -> dict[str, Any]:
    """Κατέβασμα πρωτοκόλλων Ergani + 1-1 απαγωγή για προηγούμενη ημέρα εργασίας."""
    from app.protocol_deduction_match import apply_protocol_sync

    ctx = store_api_context(cfg)
    sid = int(cfg["id"])
    name = str(cfg.get("name") or sid)
    run_id = str(uuid.uuid4())
    from_iso = str(target_date_iso).strip()[:10]
    to_iso = str(protocol_to_iso).strip()[:10]
    log = KartaLogger(
        OPERATION_NIGHTLY_PROTOCOL_SYNC,
        store_id=sid,
        store_name=name,
        run_id=run_id,
        extra={
            "employer_afm": ctx.get("employer_afm"),
            "branch_aa": ctx.get("branch_aa"),
            "target_date": from_iso,
            "protocol_to": to_iso,
        },
    )
    log.info(
        f"Νυχτερινό sync πρωτοκόλλων για {from_iso} (download έως {to_iso})",
        target_date=from_iso,
    )
    try:
        card_protocol = sync_card_protocols_from_portal(
            ctx,
            from_iso=from_iso,
            to_iso=to_iso,
            max_days=max(1, (datetime.strptime(to_iso, "%Y-%m-%d").date() - datetime.strptime(from_iso, "%Y-%m-%d").date()).days + 1),
            run_id=run_id,
        )
        _log_portal_phase(log, "Πρωτόκολλα Ergani", card_protocol)
        protocol_match = apply_protocol_sync(
            sid,
            str(ctx.get("employer_afm") or ""),
            str(ctx.get("branch_aa") or "0"),
            from_iso=from_iso,
            to_iso=to_iso,
        )
        wl_upd = int(protocol_match.get("work_log_updated") or 0)
        if wl_upd > 0 or int(protocol_match.get("declaration_updated") or 0) > 0:
            log.info(protocol_match.get("detail") or "1-1 απαγωγή OK")
        else:
            log.info(
                protocol_match.get("detail") or "1-1 απαγωγή: καμία ενημέρωση",
                matched=protocol_match.get("matched"),
            )
        ok = bool(card_protocol.get("success"))
        detail = (
            f"πρωτόκολλα {card_protocol.get('count', 0)}, "
            f"1-1 πραγματική {wl_upd}, δηλώσεις {protocol_match.get('declaration_updated', 0)}"
        )
        repo_sync_log.finish_run(
            run_id,
            status="done" if ok else "error",
            message=detail,
            result={
                "success": ok,
                "target_date": from_iso,
                "card_protocol": card_protocol,
                "protocol_match": protocol_match,
            },
        )
        return {
            "success": ok,
            "target_date": from_iso,
            "detail": detail,
            "card_protocol": card_protocol,
            "protocol_match": protocol_match,
        }
    except Exception as ex:
        err = str(ex)
        log.error(f"Σφάλμα νυχτερινού sync πρωτοκόλλων: {err}")
        repo_sync_log.finish_run(
            run_id,
            status="error",
            message=err,
            result={"success": False, "target_date": from_iso, "error": err},
        )
        return {"success": False, "target_date": from_iso, "error": err}


def should_run_weekly_repair_work_log_sync(
    cfg: dict[str, Any],
    *,
    now: datetime | None = None,
) -> tuple[bool, str, str, str]:
    local_now = (now or datetime.now(tz_athens())).astimezone(tz_athens())
    if not Config.KARTA_SCHEDULED_WEEKLY_REPAIR_ENABLED:
        return False, "", "", "απενεργοποιημένο από ρύθμιση"
    weekday = int(Config.KARTA_SCHEDULED_WEEKLY_REPAIR_WEEKDAY or 6)
    days = max(1, int(Config.KARTA_SCHEDULED_WEEKLY_REPAIR_DAYS or 90))
    base_date = local_now.date().isoformat()
    from_iso = _add_iso_days(base_date, -(days - 1))
    to_iso = base_date
    if local_now.weekday() != weekday:
        return False, from_iso, to_iso, "δεν είναι ημέρα weekly repair"
    run_time = _normalized_sync_time(
        Config.KARTA_SCHEDULED_WEEKLY_REPAIR_TIME,
        default="05:00",
    )
    if local_now.strftime("%H:%M") < run_time:
        return False, from_iso, to_iso, f"αναμονή μέχρι {run_time}"
    if not repo_sync_log.tables_available():
        return False, from_iso, to_iso, "λείπουν πίνακες sync log για εβδομαδιαίο guard"
    if _operation_run_exists(
        OPERATION_WEEKLY_REPAIR_WORK_LOG_SYNC,
        int(cfg["id"]),
        base_date,
    ):
        return False, from_iso, to_iso, "έχει ήδη εκτελεστεί αυτή την Κυριακή"
    return True, from_iso, to_iso, "έτοιμο"


def should_run_employment_contract_sync(
    cfg: dict[str, Any],
    *,
    now: datetime | None = None,
) -> tuple[bool, str]:
    local_now = (now or datetime.now(tz_athens())).astimezone(tz_athens())
    if not Config.KARTA_SCHEDULED_EMPLOYMENT_CONTRACT_ENABLED:
        return False, "απενεργοποιημένο από ρύθμιση"
    base_date = local_now.date().isoformat()
    run_time = _normalized_sync_time(
        Config.KARTA_SCHEDULED_EMPLOYMENT_CONTRACT_TIME,
        default="04:00",
    )
    if local_now.strftime("%H:%M") < run_time:
        return False, f"αναμονή μέχρι {run_time}"
    if not repo_sync_log.tables_available():
        return False, "λείπουν πίνακες sync log για ημερήσιο guard"
    if _operation_run_exists(
        OPERATION_EMPLOYMENT_CONTRACT_SYNC,
        int(cfg["id"]),
        base_date,
    ):
        return False, "έχει ήδη εκτελεστεί σήμερα"
    return True, "έτοιμο"


def should_run_apologistic_snapshot(
    cfg: dict[str, Any], *, now: datetime | None = None,
) -> tuple[bool, str]:
    """Monday 03:00 guard; missing/failed stores retry on subsequent scheduler passes."""
    from app.apologistic import previous_week
    from app import repo_apologistic

    local_now = (now or datetime.now(tz_athens())).astimezone(tz_athens())
    if not Config.KARTA_SCHEDULED_APOLOGISTIC_ENABLED:
        return False, "απενεργοποιημένο από ρύθμιση"
    if local_now.weekday() != int(Config.KARTA_SCHEDULED_APOLOGISTIC_WEEKDAY or 0):
        return False, "δεν είναι ημέρα παραγωγής απολογιστικού"
    run_time = _normalized_sync_time(Config.KARTA_SCHEDULED_APOLOGISTIC_TIME, default="03:00")
    if local_now.strftime("%H:%M") < run_time:
        return False, f"αναμονή μέχρι {run_time}"
    if not repo_apologistic.tables_available():
        return False, "λείπουν οι πίνακες απολογιστικού"
    week_from, _ = previous_week(local_now.date())
    run = repo_apologistic.get_run(int(cfg["id"]), week_from)
    if run and run.get("status") in ("draft", "approved", "locked"):
        return False, "η προηγούμενη εβδομάδα έχει ήδη παραχθεί"
    return True, "έτοιμο"


def run_employment_contract_sync_for_store(cfg: dict[str, Any]) -> dict[str, Any]:
    from app.portal_employment_contract_sync import sync_employment_contracts_from_portal

    ctx = store_api_context(cfg)
    sid = int(cfg["id"])
    name = str(cfg.get("name") or sid)
    run_id = str(uuid.uuid4())
    log = KartaLogger(
        OPERATION_EMPLOYMENT_CONTRACT_SYNC,
        store_id=sid,
        store_name=name,
        run_id=run_id,
        extra={
            "employer_afm": ctx.get("employer_afm"),
            "branch_aa": ctx.get("branch_aa"),
        },
    )
    log.info("Έναρξη ημερήσιου συγχρονισμού στοιχείων σύμβασης")
    try:
        result = sync_employment_contracts_from_portal(ctx, run_id=run_id)
        ok = bool(result.get("success"))
        detail = result.get("detail") or "Συγχρονισμός στοιχείων σύμβασης"
        log.info(detail, success=ok, count=result.get("count"))
        repo_sync_log.finish_run(
            run_id,
            status="done" if ok else "error",
            message=detail,
            result={"success": ok, "employment_contract": result},
        )
        return {"success": ok, "employment_contract": result}
    except Exception as ex:
        err = str(ex)
        log.error(f"Σφάλμα συγχρονισμού σύμβασης: {err}")
        repo_sync_log.finish_run(
            run_id,
            status="error",
            message=err,
            result={"success": False, "error": err},
        )
        return {"success": False, "error": err}


def run_work_log_range_sync_for_store(
    cfg: dict[str, Any],
    *,
    from_iso: str,
    to_iso: str,
    operation: str,
) -> dict[str, Any]:
    ctx = store_api_context(cfg)
    sid = int(cfg["id"])
    name = str(cfg.get("name") or sid)
    run_id = str(uuid.uuid4())
    days = max(1, (datetime.strptime(to_iso, "%Y-%m-%d").date() - datetime.strptime(from_iso, "%Y-%m-%d").date()).days + 1)
    log = KartaLogger(
        operation,
        store_id=sid,
        store_name=name,
        run_id=run_id,
        extra={
            "employer_afm": ctx.get("employer_afm"),
            "branch_aa": ctx.get("branch_aa"),
            "from_iso": from_iso,
            "to_iso": to_iso,
            "days": days,
        },
    )
    log.info(
        f"Έναρξη συγχρονισμού πραγματικής {from_iso} – {to_iso}",
        from_iso=from_iso,
        to_iso=to_iso,
        days=days,
    )
    try:
        result = sync_work_log_from_portal(
            ctx,
            from_iso=from_iso,
            to_iso=to_iso,
            max_days=days,
            run_id=run_id,
        )
        _log_portal_phase(log, "Πραγματική απασχόληση", result)
        ok = bool(result.get("success"))
        repo_sync_log.finish_run(
            run_id,
            status="done" if ok else "error",
            message=result.get("detail") or "Συγχρονισμός πραγματικής",
            result={
                "success": ok,
                "from_iso": from_iso,
                "to_iso": to_iso,
                "work_log": result,
            },
        )
        return {
            "success": ok,
            "from_iso": from_iso,
            "to_iso": to_iso,
            "days": days,
            "work_log": result,
        }
    except Exception as ex:
        err = str(ex)
        log.error(f"Σφάλμα συγχρονισμού πραγματικής: {err}")
        repo_sync_log.finish_run(
            run_id,
            status="error",
            message=err,
            result={
                "success": False,
                "from_iso": from_iso,
                "to_iso": to_iso,
                "days": days,
                "error": err,
            },
        )
        return {
            "success": False,
            "from_iso": from_iso,
            "to_iso": to_iso,
            "days": days,
            "error": err,
        }


def run_future_schedule_sync_for_store(
    cfg: dict[str, Any],
    *,
    from_iso: str,
    to_iso: str,
) -> dict[str, Any]:
    ctx = store_api_context(cfg)
    sid = int(cfg["id"])
    name = str(cfg.get("name") or sid)
    run_id = str(uuid.uuid4())
    log = KartaLogger(
        OPERATION_FUTURE_SCHEDULE_SYNC,
        store_id=sid,
        store_name=name,
        run_id=run_id,
        extra={
            "employer_afm": ctx.get("employer_afm"),
            "branch_aa": ctx.get("branch_aa"),
            "from_iso": from_iso,
            "to_iso": to_iso,
        },
    )
    log.info(
        f"Έναρξη συγχρονισμού μελλοντικού ψηφιακού ωραρίου {from_iso} – {to_iso}",
        from_iso=from_iso,
        to_iso=to_iso,
    )
    try:
        result = sync_schedule_from_portal(
            ctx,
            from_iso=from_iso,
            to_iso=to_iso,
            max_days=FUTURE_SCHEDULE_LOOKAHEAD_DAYS,
            run_id=run_id,
        )
        _log_portal_phase(log, "Μελλοντικό ψηφιακό ωράριο", result)
        ok = bool(result.get("success"))
        repo_sync_log.finish_run(
            run_id,
            status="done" if ok else "error",
            message=result.get("detail") or "Μελλοντικό ψηφιακό ωράριο",
            result={
                "success": ok,
                "from_iso": from_iso,
                "to_iso": to_iso,
                "schedule": result,
            },
        )
        return {
            "success": ok,
            "from_iso": from_iso,
            "to_iso": to_iso,
            "schedule": result,
        }
    except Exception as ex:
        err = str(ex)
        log.error(f"Σφάλμα μελλοντικού ψηφιακού ωραρίου: {err}")
        repo_sync_log.finish_run(
            run_id,
            status="error",
            message=err,
            result={
                "success": False,
                "from_iso": from_iso,
                "to_iso": to_iso,
                "error": err,
            },
        )
        return {
            "success": False,
            "from_iso": from_iso,
            "to_iso": to_iso,
            "error": err,
        }


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
        return {
            "schedule_last_sync_at": None,
            "work_log_last_sync_at": None,
        }

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
    operation: str | None = None,
    run_configured_auto_actions: bool = True,
) -> dict[str, Any]:
    """Συγχρονισμός μίας ημέρας (προεπιλογή σήμερα): ωράριο + πραγματική + καταγραφή."""
    ctx = store_api_context(cfg)
    today = (work_date_iso or _today_iso()).strip()[:10]
    sid = int(cfg["id"])
    name = str(cfg.get("name") or sid)
    run_id = str(uuid.uuid4())
    op = (operation or OPERATION).strip() or OPERATION

    # 00:00–02:59: syncάρουμε και χθες για overnight (*) εγγραφές.
    local_now = datetime.now(tz_athens())
    _include_previous_day = local_now.hour < 3 and not work_date_iso
    sync_from = _add_iso_days(today, -1) if _include_previous_day else today
    sync_days = 2 if _include_previous_day else 1

    log = KartaLogger(
        op,
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
            from_iso=sync_from,
            to_iso=today,
            max_days=sync_days,
            run_id=run_id,
        )
        _log_portal_phase(log, "Ψηφιακό ωράριο", schedule)

        log.info("Φάση 2/2: πραγματική απασχόληση (portal)…")
        work_log = sync_work_log_from_portal(
            ctx,
            from_iso=sync_from,
            to_iso=today,
            max_days=sync_days,
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

    post_sync_notifications_enqueued = False
    if ok and op == OPERATION:
        post_sync_notifications_enqueued = enqueue_post_sync_notifications(
            cfg,
            work_date_iso=today,
            parent_run_id=run_id,
        )
        if post_sync_notifications_enqueued:
            log.info("Έγινε enqueue ασύγχρονων ειδοποιήσεων μετά το sync")

    auto_actions = None
    if op == OPERATION and run_configured_auto_actions:
        try:
            refreshed_cfg = repo_store.get_store_config(sid) or cfg
            auto_actions = _run_configured_auto_actions(
                refreshed_cfg,
                parent_run_id=run_id,
                enqueue_auto_close=True,
            )
            if auto_actions and auto_actions.get("_auto_close_job"):
                log.info("Έγινε enqueue ασύγχρονου auto-close προηγούμενης ημέρας")
        except Exception as ex:
            auto_actions = {"auto_close_prev_day": {"success": False, "error": str(ex)}}
            log.error(f"Σφάλμα αυτόματων ενεργειών: {ex}")

    result = {
        "store_id": sid,
        "store_name": name,
        "work_date": today,
        "run_id": run_id,
        "success": ok,
        "detail": detail,
        "schedule": schedule,
        "work_log": work_log,
        "post_sync_notifications_enqueued": post_sync_notifications_enqueued,
        "auto_actions": auto_actions,
        "schedule_last_sync_at": sync_times.get("schedule_last_sync_at"),
        "work_log_last_sync_at": sync_times.get("work_log_last_sync_at"),
    }
    if auto_actions and auto_actions.get("_auto_close_job"):
        result["_auto_close_job"] = auto_actions["_auto_close_job"]
        auto_actions = dict(auto_actions)
        auto_actions.pop("_auto_close_job", None)
        result["auto_actions"] = auto_actions
    _finish_store_run(
        run_id,
        ok=ok,
        message=f"{name}: {summary}",
        result=result,
    )
    return result


def enqueue_sync_store_today_after_card(
    cfg: dict[str, Any],
    *,
    work_date_iso: str,
) -> bool:
    """
    Απενεργοποιημένο.

    Μετά από επιτυχή κάρτα η τοπική εικόνα ενημερώνεται από την καταχώρηση
    που μόλις κάναμε, όχι με delayed portal sync πραγματικής απασχόλησης.
    """
    return False


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


def _login_sync_key(user_id: int | None, store_ids: list[int] | None) -> str:
    if store_ids is None:
        scope = "all"
    else:
        scope = ",".join(str(x) for x in sorted({int(s) for s in store_ids}))
    return f"user:{user_id or 'fallback'}|stores:{scope}"


def enqueue_sync_allowed_stores_after_login(
    *,
    user_id: int | None,
    store_ids: list[int] | None,
) -> bool:
    """
    Μετά από login γραφείου, τρέχει background sync για τα καταστήματα του χρήστη.
    `store_ids=None` σημαίνει όλα τα syncable stores, δηλαδή `super_admin`.
    """
    if store_ids is not None and not {int(x) for x in store_ids}:
        return False
    key = _login_sync_key(user_id, store_ids)
    now = time.time()
    with _after_login_sync_lock:
        last = _after_login_sync_seen.get(key)
        if last and now - last < AFTER_LOGIN_SYNC_COOLDOWN_SECONDS:
            return False
        _after_login_sync_seen[key] = now

    ids_snapshot = None if store_ids is None else sorted({int(x) for x in store_ids})

    def _run() -> None:
        try:
            run_scheduled_sync(
                store_ids=ids_snapshot,
                skip_if_running=True,
                run_configured_auto_actions=False,
            )
        except Exception:
            pass

    threading.Thread(
        target=_run,
        daemon=True,
        name=f"login-sync-{user_id or 'all'}",
    ).start()
    return True


def run_scheduled_sync(
    *,
    store_ids: list[int] | None = None,
    work_date_iso: str | None = None,
    dry_run: bool = False,
    skip_if_running: bool = True,
    run_configured_auto_actions: bool = True,
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
    pending_auto_close: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for cfg in stores:
        row = sync_store_today(
            cfg,
            work_date_iso=today,
            run_configured_auto_actions=run_configured_auto_actions,
        )
        job = row.pop("_auto_close_job", None)
        if job:
            pending_auto_close.append((row, job))
        results.append(row)

    for row, job in pending_auto_close:
        try:
            job["thread"].join()
        except Exception:
            pass
        result = job.get("holder", {}).get("result") or {
            "success": False,
            "work_date": job.get("work_date"),
            "submitted": 0,
            "failed": 0,
            "error": "ασύγχρονο auto-close χωρίς αποτέλεσμα",
        }
        actions = row.get("auto_actions") if isinstance(row.get("auto_actions"), dict) else {}
        actions["auto_close_prev_day"] = result
        row["auto_actions"] = actions

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
