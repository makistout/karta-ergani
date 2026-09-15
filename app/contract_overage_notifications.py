"""Αυτόματη αποστολή υπερβάσεων σύμβασης στους λήπτες — προηγούμενο βράδυ για αύριο."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from app.contract_home_alerts import (
    CODE_HOURS_OVER,
    CODE_LEAVE_OVER,
    CODE_SIXTH_DAY,
    enrich_card_report_rows_with_contract_alerts,
)
from app.date_util import format_date_for_ergani
from app.ergani_env import store_api_context
from app.karta_log import KartaLogger
from app.work_card_payload import norm_afm, tz_athens
from app import repo_sync_log
from config import Config

OPERATION_CONTRACT_OVERAGE_NOTIFY = "scheduled_contract_overage_notify"

_ALERT_TITLE = {
    CODE_SIXTH_DAY: "6η εργάσιμη σε 5ήμερη",
    CODE_HOURS_OVER: "Υπέρβαση εβδομαδιαίων ωρών",
    CODE_LEAVE_OVER: "Υπέρβαση κανονικής άδειας",
}


def should_run_contract_overage_notify(
    cfg: dict[str, Any],
    *,
    now: datetime | None = None,
) -> tuple[bool, str, str]:
    """Επιστρέφει (τρέχει, ISO ημερομηνία στόχου=αύριο, λόγος)."""
    from app.scheduled_sync import (
        _add_iso_days,
        _normalized_sync_time,
        _operation_run_exists,
    )

    local_now = (now or datetime.now(tz_athens())).astimezone(tz_athens())
    if not Config.KARTA_SCHEDULED_CONTRACT_OVERAGE_NOTIFY_ENABLED:
        return False, "", "απενεργοποιημένο από ρύθμιση"
    base_date = local_now.date().isoformat()
    target_iso = _add_iso_days(base_date, 1)
    run_time = _normalized_sync_time(
        Config.KARTA_SCHEDULED_CONTRACT_OVERAGE_NOTIFY_TIME,
        default="21:00",
    )
    if local_now.strftime("%H:%M") < run_time:
        return False, target_iso, f"αναμονή μέχρι {run_time}"
    if not repo_sync_log.tables_available():
        return False, target_iso, "λείπουν πίνακες sync log"
    if _operation_run_exists(
        OPERATION_CONTRACT_OVERAGE_NOTIFY,
        int(cfg["id"]),
        base_date,
    ):
        return False, target_iso, "έχει ήδη εκτελεστεί σήμερα"
    return True, target_iso, "έτοιμο"


def _employee_display_name(row: dict[str, Any]) -> str:
    name = f"{(row.get('eponymo') or '').strip()} {(row.get('onoma') or '').strip()}".strip()
    return name or str(row.get("employee_afm") or "—")


def collect_contract_overages_for_date(
    cfg: dict[str, Any],
    *,
    date_iso: str,
) -> list[dict[str, Any]]:
    """Εργαζόμενοι με τουλάχιστον μία παράβαση σύμβασης για την ημερομηνία."""
    from app.card_report import build_card_status_report

    ctx = store_api_context(cfg)
    report = build_card_status_report(
        str(ctx.get("employer_afm") or ""),
        str(ctx.get("branch_aa") or "0"),
        date_iso=date_iso,
    )
    rows = list(report.get("rows") or [])
    for row in rows:
        row["work_date"] = report.get("work_date") or format_date_for_ergani(date_iso)
    enrich_card_report_rows_with_contract_alerts(
        rows,
        store_id=int(cfg["id"]),
        employer_afm=str(ctx.get("employer_afm") or ""),
        branch_aa=str(ctx.get("branch_aa") or "0"),
    )
    hits: list[dict[str, Any]] = []
    for row in rows:
        alerts = [
            a
            for a in (row.get("contract_alerts") or [])
            if isinstance(a, dict) and str(a.get("code") or "") in _ALERT_TITLE
        ]
        if not alerts:
            continue
        afm = norm_afm(str(row.get("employee_afm") or ""))
        if not afm:
            continue
        hits.append({
            "employee_afm": afm,
            "name": _employee_display_name(row),
            "alerts": alerts,
        })
    hits.sort(key=lambda item: item["name"].upper())
    return hits


def format_contract_overage_digest(
    *,
    store_name: str,
    work_date_ergani: str,
    hits: list[dict[str, Any]],
) -> str:
    store = (store_name or "").strip() or "κατάστημα"
    lines = [
        f"erganiOS — {store}",
        f"Υπερβάσεις σύμβασης για αύριο ({work_date_ergani}):",
        "",
    ]
    for hit in hits:
        name = hit.get("name") or hit.get("employee_afm")
        afm = hit.get("employee_afm") or "—"
        for alert in hit.get("alerts") or []:
            label = str(alert.get("label") or "").strip() or _ALERT_TITLE.get(
                str(alert.get("code") or ""),
                "Παράβαση σύμβασης",
            )
            lines.append(f"• {name} (ΑΦΜ {afm}): {label}")
    return "\n".join(lines)


def _send_digest_to_recipients(
    *,
    store_id: int,
    store_name: str,
    work_date_ergani: str,
    text: str,
    hits: list[dict[str, Any]],
) -> dict[str, Any]:
    from app.email_notify import EmailNotConfigured, send_notification_email
    from app.repo_notify_recipients import (
        list_deliverable_recipients,
        list_email_deliverable_recipients,
    )
    from app.telegram_notify import TelegramNotConfigured, send_telegram_message

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

    detail_rows = []
    for hit in hits:
        for alert in hit.get("alerts") or []:
            detail_rows.append((
                f"{hit.get('name')} ({hit.get('employee_afm')})",
                str(alert.get("label") or ""),
            ))

    for rec in email_recipients:
        email = str(rec.get("email") or "").strip()
        if not email:
            continue
        try:
            send_notification_email(
                email,
                "erganiOS — Υπερβάσεις σύμβασης αύριο",
                title="Υπερβάσεις σύμβασης για αύριο",
                preheader=f"{store_name} · {work_date_ergani}",
                store_name=store_name,
                employee_name="—",
                employee_afm=None,
                work_date=work_date_ergani,
                problem=(
                    f"Βρέθηκαν {len(hits)} εργαζόμενοι με παράβαση σύμβασης "
                    f"για αύριο ({work_date_ergani})."
                ),
                details=detail_rows[:40],
                footer_note=(
                    "Η ειδοποίηση στέλνεται αυτόματα στις 21:00 της προηγούμενης ημέρας."
                ),
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
        "recipient_total": len(telegram_recipients) + len(email_recipients),
    }


def run_contract_overage_notify_for_store(
    cfg: dict[str, Any],
    *,
    target_date_iso: str,
    parent_run_id: str | None = None,
) -> dict[str, Any]:
    sid = int(cfg["id"])
    name = str(cfg.get("name") or sid)
    target = str(target_date_iso).strip()[:10]
    work_date_ergani = format_date_for_ergani(target)
    # Ξεχωριστό run_id ώστε το ημερήσιο guard (_operation_run_exists) να δουλεύει.
    _ = parent_run_id
    log = KartaLogger(
        OPERATION_CONTRACT_OVERAGE_NOTIFY,
        store_id=sid,
        store_name=name,
        run_id=str(uuid.uuid4()),
        extra={"target_date": target},
    )
    try:
        hits = collect_contract_overages_for_date(cfg, date_iso=target)
        if not hits:
            detail = f"Καμία υπέρβαση σύμβασης για {work_date_ergani}"
            log.info(detail, target_date=target, hits=0)
            repo_sync_log.finish_run(
                log.run_id,
                status="done",
                message=detail,
                result={
                    "success": True,
                    "skipped": True,
                    "reason": "no_overages",
                    "target_date": target,
                    "hits": 0,
                    "sent": 0,
                },
            )
            return {
                "success": True,
                "skipped": True,
                "reason": "no_overages",
                "target_date": target,
                "hits": 0,
                "sent": 0,
            }

        text = format_contract_overage_digest(
            store_name=name,
            work_date_ergani=work_date_ergani,
            hits=hits,
        )
        delivery = _send_digest_to_recipients(
            store_id=sid,
            store_name=name,
            work_date_ergani=work_date_ergani,
            text=text,
            hits=hits,
        )
        detail = (
            f"Υπερβάσεις αύριο {work_date_ergani}: {len(hits)} εργαζόμενοι, "
            f"αποστολές {delivery.get('sent', 0)}"
        )
        log.info(
            detail,
            target_date=target,
            hits=len(hits),
            telegram_sent=delivery.get("telegram_sent"),
            email_sent=delivery.get("email_sent"),
        )
        if delivery.get("errors"):
            for err in delivery["errors"][:10]:
                log.error(str(err))
        repo_sync_log.finish_run(
            log.run_id,
            status="done",
            message=detail,
            result={
                "success": True,
                "target_date": target,
                "hits": len(hits),
                "delivery": delivery,
            },
        )
        return {
            "success": True,
            "target_date": target,
            "hits": len(hits),
            "sent": int(delivery.get("sent") or 0),
            "delivery": delivery,
        }
    except Exception as ex:
        err = str(ex)
        log.error(f"Σφάλμα αποστολής υπερβάσεων σύμβασης: {err}")
        repo_sync_log.finish_run(
            log.run_id,
            status="error",
            message=err,
            result={"success": False, "target_date": target, "error": err},
        )
        return {"success": False, "target_date": target, "error": err}
