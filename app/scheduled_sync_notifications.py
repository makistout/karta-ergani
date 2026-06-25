"""Post-sync notification worker for scheduled sync."""

from __future__ import annotations

import threading
import uuid
from typing import Any

from app.ergani_env import store_api_context
from app.karta_log import KartaLogger
from app import repo_sync_log
from config import Config

OPERATION_POST_SYNC_NOTIFY = "scheduled_post_sync_notify"
_POST_SYNC_NOTIFY_LOCK = threading.Lock()
_POST_SYNC_NOTIFY_RUNNING: set[str] = set()


def _today_iso() -> str:
    from datetime import datetime

    return datetime.today().strftime("%Y-%m-%d")


def is_store_syncable(cfg: dict[str, Any]) -> bool:
    from app.scheduled_sync import is_store_syncable as _is_store_syncable

    return _is_store_syncable(cfg)


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
        notify_rows = [
            row
            for row in rows
            if str(row.get("today_notify_kind") or "").strip()
            and not bool(row.get("today_notify_snoozed"))
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

        for idx, row in enumerate(notify_rows, start=1):
            kind = str(row.get("today_notify_kind") or "").strip()
            wl = _card_report_work_log(row)
            sched = row.get("schedule") if isinstance(row.get("schedule"), dict) else None
            employee_afm = str(row.get("employee_afm") or "").strip()
            employee_name = f"{row.get('eponymo') or ''} {row.get('onoma') or ''}".strip()
            repo_sync_log.update_run_progress(
                run_id,
                message=f"Αποστολή ειδοποίησης {idx}/{len(notify_rows)}: {employee_name or employee_afm}",
                step=idx,
                total=len(notify_rows),
            )
            log.info(
                (
                    "Αποστολή ειδοποίησης καμπάνας "
                    f"{idx}/{len(notify_rows)}: {employee_name or employee_afm} ({kind})"
                ),
                employee_afm=employee_afm,
                notify_kind=kind,
                step=idx,
                total=len(notify_rows),
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
                    log=log,
                    schedule_loaded=True,
                    schedule_hour_from=(sched or {}).get("hour_from"),
                    schedule_hour_to=(sched or {}).get("hour_to"),
                    schedule_shift_type=(sched or {}).get("shift_type"),
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
    background: bool = False,
) -> bool:
    """Post-sync ειδοποιήσεις για ένα κατάστημα.

    Προεπιλογή συγχρονή εκτέλεση — το CLI του Task Scheduler τερματίζει αμέσως
    μετά το sync και θα σκότωνε daemon thread πριν σταλούν τα μηνύματα.
    """
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

    if not background:
        try:
            _send_post_sync_notifications(
                cfg_snapshot,
                work_date_iso=ref,
                parent_run_id=parent_run_id,
            )
        finally:
            with _POST_SYNC_NOTIFY_LOCK:
                _POST_SYNC_NOTIFY_RUNNING.discard(key)
        return True

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
