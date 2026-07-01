"""Αυτόματο κλείσιμο ανοιχτών εξόδων προηγούμενης ημέρας."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from app.audit_log import record_audit_event
from app.date_util import format_date_for_ergani
from app.ergani_env import api_login_credentials, client_for_store, store_api_context
from app.http_helpers import json_or_text, response_body_text
from app.karta_log import KartaLogger
from app.repo_card import card_event_exists, persist_wrk_card_submit
from app.repo_work_log import (
    append_card_punches_missing_from_work_log,
    enrich_work_log_rows_with_card_punch,
    enrich_work_log_rows_with_schedule,
    list_work_log_for_store,
)
from app.work_card_payload import (
    RETRO_AITIOLOGIA_INTERNET,
    SUBMISSION_CODE_WRK_CARD,
    WorkCardPayloadError,
    build_wrk_card_se_payload,
    norm_afm,
    tz_athens,
)

OPERATION_AUTO_CLOSE_PREV_DAY = "auto_close_prev_day_cards"
DEFAULT_REST_DURATION_MINUTES = 8 * 60


def normalize_auto_close_time(value: str | None) -> str:
    raw = str(value or "").strip()
    try:
        hh, mm = raw.split(":", 1)
        h = int(hh)
        m = int(mm)
    except (TypeError, ValueError):
        return "00:30"
    if h < 0 or h > 23 or m < 0 or m > 59:
        return "00:30"
    return f"{h:02d}:{m:02d}"


def should_run_auto_close_prev_day(
    cfg: dict[str, Any],
    *,
    now: datetime | None = None,
) -> tuple[bool, str, str]:
    """Επιστρέφει (τρέχει, χθεσινή ISO, λόγος)."""
    if not bool(cfg.get("auto_close_prev_day_enabled")):
        return False, "", "ρύθμιση ανενεργή"
    local_now = (now or datetime.now(tz_athens())).astimezone(tz_athens())
    previous_day = (local_now.date() - timedelta(days=1)).isoformat()
    if str(cfg.get("auto_close_prev_day_last_run_date") or "").strip() == previous_day:
        return False, previous_day, "έχει ήδη εκτελεστεί για την προηγούμενη ημέρα"
    run_time = normalize_auto_close_time(str(cfg.get("auto_close_prev_day_time") or "00:30"))
    now_hm = local_now.strftime("%H:%M")
    if now_hm < run_time:
        return False, previous_day, f"αναμονή μέχρι {run_time}"
    return True, previous_day, "έτοιμο"


def _parse_clock_minutes(value: str | None) -> int | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    parts = raw.split(":")
    if len(parts) < 2:
        return None
    try:
        h = int(parts[0])
        m = int(parts[1])
    except ValueError:
        return None
    if h < 0 or h > 23 or m < 0 or m > 59:
        return None
    return h * 60 + m


def _format_minutes_as_clock(total_minutes: int) -> str:
    wrapped = int(total_minutes) % (24 * 60)
    h, m = divmod(wrapped, 60)
    return f"{h:02d}:{m:02d}"


def _duration_between(start: int | None, end: int | None) -> int | None:
    if start is None or end is None:
        return None
    duration = end - start
    if duration < 0:
        duration += 24 * 60
    return duration if duration > 0 else None


def _schedule_duration_minutes(row: dict[str, Any]) -> int | None:
    durations: list[int] = []
    slots = row.get("schedule_slots")
    if isinstance(slots, list):
        for slot in slots:
            if not isinstance(slot, dict):
                continue
            dur = _duration_between(
                _parse_clock_minutes(slot.get("hour_from")),
                _parse_clock_minutes(slot.get("hour_to")),
            )
            if dur:
                durations.append(dur)
    if not durations:
        sched = row.get("schedule")
        if isinstance(sched, dict):
            dur = _duration_between(
                _parse_clock_minutes(sched.get("hour_from")),
                _parse_clock_minutes(sched.get("hour_to")),
            )
            if dur:
                durations.append(dur)
    return sum(durations) if durations else None


def _row_is_active(row: dict[str, Any]) -> bool:
    v = row.get("employee_active")
    return not (v is False or v == 0 or v == "0")


def _build_previous_day_close_plan(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    plan: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for row in rows:
        afm = str(row.get("employee_afm") or "").strip()
        name = f"{row.get('eponymo') or ''} {row.get('onoma') or ''}".strip() or afm
        hour_from = str(row.get("hour_from") or "").strip()
        hour_to = str(row.get("hour_to") or "").strip()
        if not afm or not hour_from or hour_to:
            continue
        if not _row_is_active(row):
            skipped.append({"employee_afm": afm, "employee_name": name, "reason": "ανενεργός εργαζόμενος"})
            continue
        work_date_iso = str(row.get("work_date_iso") or "").strip()
        if not work_date_iso:
            skipped.append({"employee_afm": afm, "employee_name": name, "reason": "άγνωστη ημερομηνία"})
            continue
        entry_min = _parse_clock_minutes(hour_from)
        if entry_min is None:
            skipped.append({"employee_afm": afm, "employee_name": name, "reason": "μη έγκυρη ώρα εισόδου"})
            continue
        duration = _schedule_duration_minutes(row) or DEFAULT_REST_DURATION_MINUTES
        exit_abs = entry_min + duration
        reference_date = work_date_iso
        if exit_abs >= 24 * 60:
            reference_date = (datetime.strptime(work_date_iso, "%Y-%m-%d").date() + timedelta(days=1)).isoformat()
        if card_event_exists(afm, reference_date, "1"):
            skipped.append({"employee_afm": afm, "employee_name": name, "reason": "υπάρχει ήδη έξοδος κάρτας"})
            continue
        plan.append({
            "employee_afm": afm,
            "employee_name": name,
            "employee_last_name": str(row.get("eponymo") or "").strip(),
            "employee_first_name": str(row.get("onoma") or "").strip(),
            "work_date_iso": work_date_iso,
            "reference_date": reference_date,
            "retro_time": _format_minutes_as_clock(exit_abs),
            "duration_minutes": duration,
            "duration_source": "schedule" if _schedule_duration_minutes(row) else "rest_8h",
            "hour_from": hour_from,
        })
    return plan, skipped


def _load_previous_day_rows(cfg: dict[str, Any], work_date_iso: str) -> list[dict[str, Any]]:
    ctx = store_api_context(cfg)
    work_date = format_date_for_ergani(work_date_iso)
    rows = list_work_log_for_store(ctx["employer_afm"], ctx["branch_aa"], work_date, limit=5000)
    append_card_punches_missing_from_work_log(rows, ctx["employer_afm"], ctx["branch_aa"], [work_date])
    enrich_work_log_rows_with_schedule(rows, ctx["employer_afm"], ctx["branch_aa"], [work_date])
    enrich_work_log_rows_with_card_punch(rows, ctx["employer_afm"], ctx["branch_aa"])
    for row in rows:
        row["work_date_iso"] = work_date_iso
    return rows


def format_auto_close_notification_text(
    *,
    store_name: str,
    work_date_iso: str,
    submitted: int,
    failed: int,
    skipped: int,
    plan_count: int,
) -> str:
    work_date = format_date_for_ergani(work_date_iso)
    status = "ολοκληρώθηκε" if failed == 0 else "ολοκληρώθηκε με αποτυχίες"
    return "\n".join([
        f"erganiOS — {store_name}",
        f"Το αυτόματο κλείσιμο ανοιχτών καρτών για {work_date} {status}.",
        f"Υποβολές εξόδου: {submitted}/{plan_count}",
        f"Αποτυχίες: {failed}",
        f"Εκτός/παράλειψη: {skipped}",
    ])


def _send_auto_close_notification(
    *,
    store_id: int,
    store_name: str,
    work_date_iso: str,
    submitted: int,
    failed: int,
    skipped_count: int,
    plan_count: int,
) -> dict[str, Any]:
    from app.email_notify import EmailNotConfigured, send_notification_email
    from app.repo_notify_recipients import (
        list_deliverable_recipients,
        list_email_deliverable_recipients,
    )
    from app.telegram_notify import TelegramNotConfigured, send_telegram_message

    text = format_auto_close_notification_text(
        store_name=store_name,
        work_date_iso=work_date_iso,
        submitted=submitted,
        failed=failed,
        skipped=skipped_count,
        plan_count=plan_count,
    )
    telegram_sent = 0
    email_sent = 0
    errors: list[str] = []

    try:
        telegram_recipients = list_deliverable_recipients(store_id)
    except Exception as ex:
        telegram_recipients = []
        errors.append(f"Telegram recipients: {ex}")
    try:
        email_recipients = list_email_deliverable_recipients(store_id)
    except Exception as ex:
        email_recipients = []
        errors.append(f"Email recipients: {ex}")

    for rec in telegram_recipients:
        chat_id = str(rec.get("telegram_chat_id") or "").strip()
        if not chat_id:
            continue
        try:
            send_telegram_message(chat_id, text)
            telegram_sent += 1
        except TelegramNotConfigured as ex:
            errors.append(f"Telegram: {ex}")
            break
        except Exception as ex:
            errors.append(f"Telegram {rec.get('name')}: {ex}")

    work_date = format_date_for_ergani(work_date_iso)
    for rec in email_recipients:
        email = str(rec.get("email") or "").strip()
        if not email:
            continue
        try:
            send_notification_email(
                email,
                "erganiOS — Αυτόματο κλείσιμο καρτών",
                title="Αυτόματο κλείσιμο καρτών",
                preheader=f"{store_name} · {work_date}",
                store_name=store_name,
                employee_name="—",
                employee_afm=None,
                work_date=work_date,
                problem="Ολοκληρώθηκε η αυτόματη ενέργεια κλεισίματος ανοιχτών καρτών προηγούμενης ημέρας.",
                details=[
                    ("Υποβολές εξόδου", f"{submitted}/{plan_count}"),
                    ("Αποτυχίες", str(failed)),
                    ("Εκτός/παράλειψη", str(skipped_count)),
                ],
                footer_note="Η ειδοποίηση αφορά αυτόματη ενέργεια του scheduled sync.",
            )
            email_sent += 1
        except EmailNotConfigured as ex:
            errors.append(f"Email: {ex}")
            break
        except Exception as ex:
            errors.append(f"Email {rec.get('name')}: {ex}")

    return {
        "telegram_sent": telegram_sent,
        "email_sent": email_sent,
        "sent": telegram_sent + email_sent,
        "errors": errors,
    }


def run_auto_close_prev_day_for_store(
    cfg: dict[str, Any],
    *,
    work_date_iso: str,
    parent_run_id: str | None = None,
) -> dict[str, Any]:
    sid = int(cfg["id"])
    ctx = store_api_context(cfg)
    log = KartaLogger(
        OPERATION_AUTO_CLOSE_PREV_DAY,
        store_id=sid,
        store_name=str(cfg.get("name") or sid),
        run_id=parent_run_id,
        extra={
            "work_date": work_date_iso,
            "employer_afm": ctx.get("employer_afm"),
            "branch_aa": ctx.get("branch_aa"),
        },
    )
    rows = _load_previous_day_rows(cfg, work_date_iso)
    plan, skipped = _build_previous_day_close_plan(rows)
    if not plan:
        log.info(
            f"Αυτόματο κλείσιμο προηγούμενης ημέρας {work_date_iso}: δεν υπάρχουν ανοιχτές έξοδοι",
            skipped=len(skipped),
        )
        notification = _send_auto_close_notification(
            store_id=sid,
            store_name=str(cfg.get("name") or sid),
            work_date_iso=work_date_iso,
            submitted=0,
            failed=0,
            skipped_count=len(skipped),
            plan_count=0,
        )
        return {
            "success": True,
            "work_date": work_date_iso,
            "submitted": 0,
            "failed": 0,
            "skipped": skipped,
            "notification": notification,
        }

    client = client_for_store(cfg)
    api_user, api_pwd, api_ut = api_login_credentials(cfg)
    auth_resp = client.authenticate(api_user, api_pwd, api_ut)
    auth_data = json_or_text(auth_resp)
    bearer = auth_data.get("accessToken") if auth_resp.ok and isinstance(auth_data, dict) else None
    if not bearer:
        detail = f"Αποτυχία Ergani API login ({auth_resp.status_code})"
        log.error(detail)
        return {"success": False, "work_date": work_date_iso, "submitted": 0, "failed": len(plan), "detail": detail, "plan": plan, "skipped": skipped}

    submitted = 0
    failures: list[dict[str, Any]] = []
    for idx, item in enumerate(plan, 1):
        emp_afm = norm_afm(item["employee_afm"])
        event_at = f"{item['reference_date']}T{item['retro_time']}:00"
        try:
            payload = build_wrk_card_se_payload(
                employer_afm=ctx["employer_afm"],
                branch_aa=ctx["branch_aa"],
                employee_afm=emp_afm,
                employee_last_name=item["employee_last_name"],
                employee_first_name=item["employee_first_name"],
                event="check_out",
                reference_date=item["reference_date"],
                event_at=event_at,
                aitiologia=RETRO_AITIOLOGIA_INTERNET,
                comments="erganiOS automatic previous-day close",
            )
        except WorkCardPayloadError as ex:
            failures.append({**item, "error": str(ex)})
            continue
        resp = client.document_submit(SUBMISSION_CODE_WRK_CARD, payload, bearer)
        parsed = json_or_text(resp)
        body_text = response_body_text(resp)
        try:
            persist_wrk_card_submit(
                SUBMISSION_CODE_WRK_CARD,
                resp.status_code,
                bool(resp.ok),
                payload,
                body_text,
                None,
                None,
                None,
                client_device="erganiOS scheduled auto close",
            )
        except Exception as ex:
            failures.append({**item, "error": f"persist: {ex}"})
            continue
        record_audit_event(
            action="work_card_punch_submit",
            success=bool(resp.ok),
            http_status=int(resp.status_code or 0),
            store_id=sid,
            employer_afm=ctx["employer_afm"],
            branch_aa=ctx["branch_aa"],
            entity_type="employee",
            entity_id=emp_afm,
            details={
                "source": "auto_close_prev_day",
                "employee_afm": emp_afm,
                "employee_name": item.get("employee_name"),
                "event": "check_out",
                "reference_date": item["reference_date"],
                "event_at": event_at,
                "batch_index": idx,
                "batch_total": len(plan),
                "duration_minutes": item["duration_minutes"],
                "duration_source": item["duration_source"],
                "ergani_response": parsed if not resp.ok else None,
            },
            client_device="erganiOS scheduled auto close",
        )
        if resp.ok:
            submitted += 1
            log.info(
                f"Αυτόματο κλείσιμο {idx}/{len(plan)} OK: {item['employee_name']} {item['retro_time']}",
                employee_afm=emp_afm,
                reference_date=item["reference_date"],
            )
        else:
            failures.append({**item, "error": body_text or str(parsed)[:500]})

    failed = len(failures)
    success = failed == 0
    log.info(
        f"Αυτόματο κλείσιμο προηγούμενης ημέρας: {submitted}/{len(plan)} υποβολές",
        submitted=submitted,
        failed=failed,
        skipped=len(skipped),
    )
    notification = _send_auto_close_notification(
        store_id=sid,
        store_name=str(cfg.get("name") or sid),
        work_date_iso=work_date_iso,
        submitted=submitted,
        failed=failed,
        skipped_count=len(skipped),
        plan_count=len(plan),
    )
    if notification.get("sent"):
        log.info(
            "Στάλθηκε ειδοποίηση αυτόματου κλεισίματος",
            telegram_sent=notification.get("telegram_sent"),
            email_sent=notification.get("email_sent"),
        )
    elif notification.get("errors"):
        log.warning(
            "Δεν στάλθηκε ειδοποίηση αυτόματου κλεισίματος",
            notification_errors=notification.get("errors"),
        )
    return {
        "success": success,
        "work_date": work_date_iso,
        "submitted": submitted,
        "failed": failed,
        "plan_count": len(plan),
        "failures": failures,
        "skipped": skipped,
        "notification": notification,
    }
