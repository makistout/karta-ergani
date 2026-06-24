"""Περιοδικός συγχρονισμός όλων των καταστημάτων — ωράριο + πραγματική για σήμερα."""

from __future__ import annotations

import threading
import uuid
from datetime import datetime
from typing import Any

from app.ergani_env import store_api_context
from app.karta_log import KartaLogger
from app.portal_schedule_sync import sync_schedule_from_portal
from app.portal_work_log_sync import sync_work_log_from_portal
from app.today_notify_logic import notify_auto_send_once
from app.work_card_payload import norm_afm
from app import repo_store, repo_sync_log
from config import Config

OPERATION = "scheduled_today_sync"
OPERATION_CARD_SUBMIT = "card_submit_today_sync"
OPERATION_POST_SYNC_NOTIFY = "scheduled_post_sync_notify"
_RUNNING_GRACE_MINUTES = 15
_POST_SYNC_NOTIFY_LOCK = threading.Lock()
_POST_SYNC_NOTIFY_RUNNING: set[str] = set()


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


def _post_sync_notify_key(store_id: int, work_date_iso: str) -> str:
    return f"{int(store_id)}|{(work_date_iso or '').strip()[:10]}"


def _card_report_work_log(row: dict[str, Any]) -> dict[str, Any]:
    wl = row.get("work_log") if isinstance(row.get("work_log"), dict) else {}
    return wl or {}


def _send_post_sync_notifications(
    cfg: dict[str, Any],
    *,
    work_date_iso: str,
    parent_run_id: str | None = None,
) -> dict[str, Any]:
    """Αποστολή ειδοποιήσεων καμπάνας μετά από sync καταστήματος."""
    from app.card_report import build_card_status_report
    from app.repo_today_alert import enrich_card_report_rows_with_today_notify
    from app.repo_today_alert import list_today_notify_sent
    from app.today_alert_service import send_today_punch_notifications

    ctx = store_api_context(cfg)
    sid = int(cfg["id"])
    name = str(cfg.get("name") or sid)
    today = (work_date_iso or _today_iso()).strip()[:10]
    run_id = str(uuid.uuid4())
    log = KartaLogger(
        OPERATION_POST_SYNC_NOTIFY,
        store_id=sid,
        store_name=name,
        run_id=run_id,
        extra={
            "parent_run_id": parent_run_id,
            "employer_afm": ctx.get("employer_afm"),
            "branch_aa": ctx.get("branch_aa"),
            "work_date": today,
        },
    )
    log.info(
        f"Έναρξη ασύγχρονων ειδοποιήσεων μετά το sync για {today}",
        work_date=today,
    )

    sent_total = 0
    target_total = 0
    skipped = 0
    errors: list[str] = []
    attempted: list[dict[str, Any]] = []

    try:
        report = build_card_status_report(
            str(ctx.get("employer_afm") or ""),
            str(ctx.get("branch_aa") or "0"),
            date_iso=today,
        )
        rows = report.get("rows") or []
        enrich_card_report_rows_with_today_notify(rows, sid)
        ergani_dates = sorted(
            {
                str(r.get("work_date") or "").strip()
                for r in rows
                if str(r.get("work_date") or "").strip()
            }
        )
        already_sent = (
            list_today_notify_sent(sid, ergani_dates) if ergani_dates else set()
        )

        notify_rows = [
            row
            for row in rows
            if str(row.get("today_notify_kind") or "").strip()
            and not bool(row.get("today_notify_snoozed"))
            and not (
                notify_auto_send_once(str(row.get("today_notify_kind") or ""))
                and (
                    norm_afm(str(row.get("employee_afm") or "")),
                    str(row.get("work_date") or "").strip(),
                    str(row.get("today_notify_kind") or "").strip(),
                )
                in already_sent
            )
        ]
        if not notify_rows:
            msg = "Δεν υπάρχουν ενεργές ειδοποιήσεις καμπάνας μετά το sync"
            log.info(msg)
            result = {
                "success": True,
                "work_date": today,
                "sent": 0,
                "total": 0,
                "skipped": 0,
                "attempted": [],
                "errors": [],
            }
            repo_sync_log.finish_run(run_id, status="done", message=msg, result=result)
            return result

        for row in notify_rows:
            kind = str(row.get("today_notify_kind") or "").strip()
            wl = _card_report_work_log(row)
            employee_afm = str(row.get("employee_afm") or "").strip()
            employee_name = f"{row.get('eponymo') or ''} {row.get('onoma') or ''}".strip()
            log.info(
                f"Αποστολή ειδοποίησης καμπάνας: {employee_name or employee_afm} ({kind})",
                employee_afm=employee_afm,
                notify_kind=kind,
            )
            try:
                res = send_today_punch_notifications(
                    store_id=sid,
                    store_name=name,
                    employer_afm=str(ctx.get("employer_afm") or ""),
                    branch_aa=str(ctx.get("branch_aa") or "0"),
                    employee_afm=employee_afm,
                    eponymo=row.get("eponymo"),
                    onoma=row.get("onoma"),
                    work_date=str(row.get("work_date") or ""),
                    hour_from=wl.get("hour_from") or row.get("hour_from"),
                    hour_to=wl.get("hour_to") or row.get("hour_to"),
                    notify_kind=kind,
                    public_base_url=Config.PUBLIC_BASE_URL,
                    auto_post_sync=True,
                )
                sent = int(res.get("sent") or 0)
                total = int(res.get("total") or 0)
                sent_total += sent
                target_total += total
                if res.get("skipped"):
                    skipped += 1
                row_errors = [str(e) for e in (res.get("errors") or []) if str(e).strip()]
                errors.extend(row_errors)
                attempted.append(
                    {
                        "employee_afm": employee_afm,
                        "employee_name": employee_name,
                        "notify_kind": kind,
                        "sent": sent,
                        "total": total,
                        "skipped": res.get("skipped"),
                        "errors": row_errors,
                    }
                )
            except Exception as ex:
                err = f"{employee_afm} ({kind}): {ex}"
                errors.append(err)
                attempted.append(
                    {
                        "employee_afm": employee_afm,
                        "employee_name": employee_name,
                        "notify_kind": kind,
                        "sent": 0,
                        "total": 0,
                        "errors": [str(ex)],
                    }
                )
                log.error(f"Αποτυχία ειδοποίησης καμπάνας: {err}")

        ok = not errors
        summary = (
            f"Ειδοποιήσεις μετά το sync: {sent_total}/{target_total} αποστολές"
            if target_total
            else "Ειδοποιήσεις μετά το sync: δεν υπάρχουν ενεργοί λήπτες"
        )
        if skipped:
            summary += f", {skipped} skipped"
        if errors:
            summary += f", {len(errors)} σφάλματα"
        log.info(summary, sent=sent_total, total=target_total, errors=len(errors))
        result = {
            "success": ok,
            "work_date": today,
            "sent": sent_total,
            "total": target_total,
            "skipped": skipped,
            "attempted": attempted,
            "errors": errors[:20],
        }
        repo_sync_log.finish_run(
            run_id,
            status="done" if ok else "error",
            message=summary,
            result=result,
        )
        return result
    except Exception as ex:
        err = str(ex)
        log.error(f"Σφάλμα post-sync ειδοποιήσεων: {err}")
        result = {
            "success": False,
            "work_date": today,
            "sent": sent_total,
            "total": target_total,
            "errors": [err],
        }
        repo_sync_log.finish_run(
            run_id,
            status="error",
            message=f"{name}: {err}",
            result=result,
        )
        return result


def enqueue_post_sync_notifications(
    cfg: dict[str, Any],
    *,
    work_date_iso: str,
    parent_run_id: str | None = None,
) -> bool:
    """Fire-and-forget post-sync ειδοποιήσεις για ένα κατάστημα."""
    if not Config.KARTA_POST_SYNC_NOTIFY_ENABLED:
        return False
    ref = (work_date_iso or "").strip()[:10]
    if not ref or ref != _today_iso():
        return False
    if not is_store_syncable(cfg):
        return False

    sid = int(cfg["id"])
    key = _post_sync_notify_key(sid, ref)
    with _POST_SYNC_NOTIFY_LOCK:
        if key in _POST_SYNC_NOTIFY_RUNNING:
            return False
        _POST_SYNC_NOTIFY_RUNNING.add(key)

    cfg_snapshot = dict(cfg)

    def _run() -> None:
        try:
            _send_post_sync_notifications(
                cfg_snapshot,
                work_date_iso=ref,
                parent_run_id=parent_run_id,
            )
        finally:
            with _POST_SYNC_NOTIFY_LOCK:
                _POST_SYNC_NOTIFY_RUNNING.discard(key)

    threading.Thread(
        target=_run,
        daemon=True,
        name=f"post-sync-notify-{sid}",
    ).start()
    return True


def sync_store_today(
    cfg: dict[str, Any],
    *,
    work_date_iso: str | None = None,
    operation: str | None = None,
) -> dict[str, Any]:
    """Συγχρονισμός μίας ημέρας (προεπιλογή σήμερα): ωράριο + πραγματική + καταγραφή."""
    ctx = store_api_context(cfg)
    today = (work_date_iso or _today_iso()).strip()[:10]
    sid = int(cfg["id"])
    name = str(cfg.get("name") or sid)
    run_id = str(uuid.uuid4())
    op = (operation or OPERATION).strip() or OPERATION

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

    post_sync_notifications_enqueued = False
    if ok and op == OPERATION:
        post_sync_notifications_enqueued = enqueue_post_sync_notifications(
            cfg,
            work_date_iso=today,
            parent_run_id=run_id,
        )
        if post_sync_notifications_enqueued:
            log.info("Έγινε enqueue ασύγχρονων ειδοποιήσεων μετά το sync")

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


def enqueue_sync_store_today_after_card(
    cfg: dict[str, Any],
    *,
    work_date_iso: str,
) -> bool:
    """
    Μετά επιτυχές χτύπημα κάρτας (π.χ. today-hit → retro-hit), συγχρονισμός
    ωραρίου + πραγματικής για σήμερα στο παρασκήνιο ώστε να ενημερωθεί η αναφορά.
    """
    ref = (work_date_iso or "").strip()[:10]
    if not ref or ref != _today_iso():
        return False
    if not is_store_syncable(cfg):
        return False

    cfg_snapshot = dict(cfg)

    def _run() -> None:
        try:
            sync_store_today(
                cfg_snapshot,
                work_date_iso=ref,
                operation=OPERATION_CARD_SUBMIT,
            )
        except Exception:
            pass

    threading.Thread(target=_run, daemon=True, name=f"card-sync-{cfg_snapshot.get('id')}").start()
    return True


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
