"""Telegram/Email notification senders for today alerts."""

from __future__ import annotations

from typing import Any

from app.repo_notify_recipients import (
    NOTIFY_REPEAT_ONCE_SNOOZE,
    list_deliverable_recipients,
    list_email_deliverable_recipients,
    normalize_notify_repeat_policy,
)
from app.repo_today_alert import (
    create_snooze,
    create_today_alert_token,
    is_notify_sent,
    is_snoozed,
    mark_notify_sent,
)
from app.repo_work_log import enrich_work_log_rows_with_schedule
from app.today_notify_logic import (
    KIND_LABELS,
    WTO_DAILY_NOTIFY_KINDS,
    card_event_blocks_today_notify,
    ergani_date_to_iso,
    merge_notify_work_hours,
    notify_auto_send_once,
    notify_db_snapshot,
    resolve_today_notify_kind,
)
from app.public_urls import ui_public_url


def build_today_hit_redirect_url(token: str | None = None) -> str:
    return ui_public_url("/ui/today-hit", token=token)


def _recipient_repeat_policy(rec: dict[str, Any]) -> str:
    return normalize_notify_repeat_policy(rec.get("notify_repeat_policy"))


def _recipient_key(rec: dict[str, Any]) -> int:
    return int(rec.get("id") or 0)


def _auto_snooze_after_send(
    *,
    rec: dict[str, Any],
    store_id: int,
    employee_afm: str,
    work_date: str,
    notify_kind: str,
    auto_post_sync: bool,
    log: Any | None = None,
    employee_name: str | None = None,
    kind_label: str | None = None,
) -> None:
    """Μία φορά ανά λήπτη: snooze αμέσως μετά την επιτυχή αποστολή."""
    if not auto_post_sync:
        return
    if _recipient_repeat_policy(rec) != NOTIFY_REPEAT_ONCE_SNOOZE:
        return
    rid = _recipient_key(rec)
    if not rid:
        return
    create_snooze(
        store_id=store_id,
        recipient_id=rid,
        employee_afm=employee_afm,
        work_date_ergani=work_date,
        notify_kind=notify_kind,
        acted_by_name="Αυτόματη αναβολή μετά από ειδοποίηση",
        acted_via="auto_post_sync",
    )
    if log is not None:
        log.info(
            "Αυτόματο snooze μετά από ειδοποίηση μίας φοράς",
            event="today_notification_auto_snooze",
            notify_kind=notify_kind,
            notify_kind_label=kind_label,
            employee_afm=employee_afm,
            employee_name=employee_name,
            work_date=work_date,
            recipient_id=rid,
            recipient_name=rec.get("name"),
        )


def _find_wto_daily_proposal(
    *,
    employer_afm: str,
    branch_aa: str,
    employee_afm: str,
    work_date_ergani: str,
    expected_kind: str | None = None,
) -> dict[str, Any] | None:
    from app.card_report import build_card_status_report

    ref_iso = ergani_date_to_iso(work_date_ergani)
    if not ref_iso:
        return None
    report = build_card_status_report(employer_afm, branch_aa, date_iso=ref_iso)
    emp = str(employee_afm or "").strip()
    for row in report.get("rows") or []:
        if str(row.get("employee_afm") or "").strip() != emp:
            continue
        wto = row.get("wto_daily")
        if not isinstance(wto, dict) or not wto.get("eligible"):
            continue
        kind = str(wto.get("kind") or "").strip()
        if expected_kind and kind != expected_kind.strip():
            continue
        return wto
    return None

def send_wto_schedule_notifications(
    *,
    store_id: int,
    store_name: str,
    employer_afm: str,
    branch_aa: str,
    employee_afm: str,
    eponymo: str | None,
    onoma: str | None,
    work_date: str,
    notify_kind: str,
    hour_from: str | None = None,
    hour_to: str | None = None,
    public_base_url: str,
) -> dict[str, Any]:
    from app.email_notify import EmailNotConfigured, send_notification_email
    from app.telegram_notify import (
        TelegramNotConfigured,
        format_today_alert_notification,
        send_telegram_message,
    )

    kind = str(notify_kind or "").strip()
    if kind not in WTO_DAILY_NOTIFY_KINDS:
        return {
            "sent": 0,
            "total": 0,
            "errors": [],
            "skipped": "invalid_kind",
        }

    proposal = _find_wto_daily_proposal(
        employer_afm=employer_afm,
        branch_aa=branch_aa,
        employee_afm=employee_afm,
        work_date_ergani=work_date,
        expected_kind=kind,
    )
    if not proposal:
        return {
            "sent": 0,
            "total": 0,
            "errors": [],
            "skipped": "no_alert",
        }

    prop_from = str(proposal.get("hour_from") or hour_from or "").strip() or None
    prop_to = str(proposal.get("hour_to") or hour_to or "").strip() or None

    recipients = list_deliverable_recipients(store_id)
    email_recipients = list_email_deliverable_recipients(store_id)
    sent = 0
    errors: list[str] = []
    ref_iso = ergani_date_to_iso(work_date)

    for rec in recipients:
        chat_id = str(rec.get("telegram_chat_id") or "").strip()
        if not chat_id:
            continue
        if is_snoozed(
            store_id=store_id,
            employee_afm=employee_afm,
            work_date_ergani=work_date,
            notify_kind=kind,
            recipient_id=int(rec["id"]),
        ):
            continue
        hit_url = None
        if (rec.get("notify_pin_hash") or "").strip():
            try:
                token = create_today_alert_token(
                    recipient_id=int(rec["id"]),
                    store_id=store_id,
                    employee_afm=employee_afm,
                    eponymo=eponymo,
                    onoma=onoma,
                    work_date_ergani=work_date,
                    reference_date_iso=ref_iso,
                    notify_kind=kind,
                    hour_from=prop_from,
                    hour_to=prop_to,
                    schedule_hour_from=None,
                )
                hit_url = build_today_hit_redirect_url(token)
            except Exception as ex:
                errors.append(f"{rec.get('name')}: token — {ex}")
        text = format_today_alert_notification(
            store_name=store_name,
            employee_afm=employee_afm,
            eponymo=eponymo,
            onoma=onoma,
            work_date=work_date,
            notify_kind=kind,
            hit_url=hit_url,
            has_pin=bool((rec.get("notify_pin_hash") or "").strip()),
            wto_hour_from=prop_from,
            wto_hour_to=prop_to,
        )
        try:
            send_telegram_message(chat_id, text)
            sent += 1
        except Exception as ex:
            errors.append(f"{rec.get('name')}: {ex}")

    employee_name = f"{(eponymo or '').strip()} {(onoma or '').strip()}".strip()
    kind_label = KIND_LABELS.get(kind, kind)
    for rec in email_recipients:
        email = str(rec.get("email") or "").strip()
        if not email:
            continue
        if is_snoozed(
            store_id=store_id,
            employee_afm=employee_afm,
            work_date_ergani=work_date,
            notify_kind=kind,
            recipient_id=int(rec["id"]),
        ):
            continue
        hit_url = None
        has_pin = bool((rec.get("notify_pin_hash") or "").strip())
        if has_pin:
            try:
                token = create_today_alert_token(
                    recipient_id=int(rec["id"]),
                    store_id=store_id,
                    employee_afm=employee_afm,
                    eponymo=eponymo,
                    onoma=onoma,
                    work_date_ergani=work_date,
                    reference_date_iso=ref_iso,
                    notify_kind=kind,
                    hour_from=prop_from,
                    hour_to=prop_to,
                    schedule_hour_from=None,
                )
                hit_url = build_today_hit_redirect_url(token)
            except Exception as ex:
                errors.append(f"Email {rec.get('name')}: token — {ex}")
        try:
            send_notification_email(
                email,
                f"erganiOS — {kind_label}",
                title=kind_label,
                preheader=f"{employee_name or employee_afm} · {work_date}",
                store_name=store_name,
                employee_name=employee_name,
                employee_afm=employee_afm,
                work_date=work_date,
                problem="Χρειάζεται ενέργεια για το ψηφιακό ωράριο/κάρτα του εργαζομένου.",
                details=[
                    ("Ώρα από", prop_from or "—"),
                    ("Ώρα έως", prop_to or "—"),
                    ("Ενέργεια", "Άνοιγμα ενέργειας" if hit_url else "Απαιτείται PIN λήπτη"),
                ],
                action_url=hit_url,
                action_label="Άνοιγμα ενέργειας",
                footer_note=(
                    "Το άνοιγμα της ενέργειας απαιτεί τον προσωπικό PIN του λήπτη."
                    if hit_url
                    else "Δεν δημιουργήθηκε σύνδεσμος επειδή δεν έχει οριστεί PIN για τον λήπτη."
                ),
            )
            sent += 1
        except EmailNotConfigured as ex:
            errors.append(f"Email {rec.get('name')}: {ex}")
        except Exception as ex:
            errors.append(f"Email {rec.get('name')}: {ex}")

    return {
        "sent": sent,
        "total": len(recipients) + len(email_recipients),
        "errors": errors,
        "notify_kind": kind,
    }


def send_today_punch_notifications(
    *,
    store_id: int,
    store_name: str,
    employer_afm: str,
    branch_aa: str,
    employee_afm: str,
    eponymo: str | None,
    onoma: str | None,
    work_date: str,
    hour_from: str | None,
    hour_to: str | None,
    notify_kind: str | None,
    public_base_url: str,
    auto_post_sync: bool = False,
    log: Any | None = None,
    schedule_loaded: bool = False,
    schedule_hour_from: str | None = None,
    schedule_hour_to: str | None = None,
    schedule_shift_type: str | None = None,
) -> dict[str, Any]:
    from app.email_notify import EmailNotConfigured, send_notification_email
    from app.telegram_notify import (
        TelegramNotConfigured,
        format_today_alert_notification,
        send_telegram_message,
    )

    hf, ht = merge_notify_work_hours(
        hour_from=hour_from,
        hour_to=hour_to,
    )
    row: dict[str, Any] = {
        "employee_afm": employee_afm,
        "work_date": work_date,
        "hour_from": hf,
        "hour_to": ht,
        "eponymo": eponymo,
        "onoma": onoma,
    }
    if schedule_loaded:
        if schedule_hour_from or schedule_hour_to or schedule_shift_type:
            row["schedule"] = {
                "hour_from": schedule_hour_from,
                "hour_to": schedule_hour_to,
                "shift_type": schedule_shift_type,
            }
        else:
            row["schedule"] = None
    else:
        enrich_work_log_rows_with_schedule(
            [row], employer_afm, branch_aa, [work_date]
        )
    sched = row.get("schedule") if isinstance(row.get("schedule"), dict) else {}
    schedule_hour_from = str((sched or {}).get("hour_from") or "").strip() or None
    schedule_hour_to = str((sched or {}).get("hour_to") or "").strip() or None

    resolved_kind = resolve_today_notify_kind(row)
    if resolved_kind and card_event_blocks_today_notify(
        employee_afm, work_date, resolved_kind
    ):
        return {
            "sent": 0,
            "total": 0,
            "errors": [],
            "skipped": "card_already_punched",
            "notify_kind": resolved_kind,
        }
    if not resolved_kind:
        return {
            "sent": 0,
            "total": 0,
            "errors": [],
            "skipped": "no_alert",
        }
    employee_name = f"{(eponymo or '').strip()} {(onoma or '').strip()}".strip()
    kind_label = KIND_LABELS.get(resolved_kind, resolved_kind)

    def log_step(message: str, **fields: Any) -> None:
        if log is None:
            return
        writer = getattr(log, "info", None)
        if writer:
            event_name = str(fields.pop("event", "today_notification_step") or "today_notification_step")
            writer(
                message,
                event=event_name,
                notify_kind=resolved_kind,
                notify_kind_label=kind_label,
                employee_afm=employee_afm,
                employee_name=employee_name,
                work_date=work_date,
                **fields,
            )

    if notify_kind and notify_kind.strip() != resolved_kind:
        return {
            "sent": 0,
            "total": 0,
            "errors": [],
            "skipped": "kind_mismatch",
        }
    log_step("Έλεγχος snooze ειδοποίησης")
    if (
        auto_post_sync
        and notify_auto_send_once(resolved_kind)
        and is_notify_sent(
            store_id=store_id,
            employee_afm=employee_afm,
            work_date_ergani=work_date,
            notify_kind=resolved_kind,
        )
    ):
        log_step("Παράλειψη — ήδη στάλθηκε αυτόματη ειδοποίηση σήμερα")
        return {
            "sent": 0,
            "total": 0,
            "errors": [],
            "skipped": "already_sent",
            "notify_kind": resolved_kind,
        }
    recipients = list_deliverable_recipients(store_id)
    email_recipients = list_email_deliverable_recipients(store_id)
    sent = 0
    errors: list[str] = []
    ref_iso = ergani_date_to_iso(work_date)

    def log_notification(
        *,
        level: str,
        message: str,
        rec: dict[str, Any],
        channel: str,
        extra: dict[str, Any] | None = None,
    ) -> None:
        if log is None:
            return
        fields = {
            "event": "today_notification_send",
            "notification_channel": channel,
            "notify_kind": resolved_kind,
            "notify_kind_label": kind_label,
            "employee_afm": employee_afm,
            "employee_name": employee_name,
            "work_date": work_date,
            "recipient_id": rec.get("id"),
            "recipient_name": rec.get("name"),
            "recipient_mobile": rec.get("mobile"),
            "recipient_email": rec.get("email"),
            "recipient_policy": _recipient_repeat_policy(rec),
        }
        if extra:
            fields.update(extra)
        writer = getattr(log, level, None) or getattr(log, "info", None)
        if writer:
            writer(message, **fields)

    log_step(
        "Έλεγχος ληπτών ειδοποίησης",
        schedule_hour_from=schedule_hour_from,
        schedule_hour_to=schedule_hour_to,
    )
    db_snapshot = notify_db_snapshot(
        employer_afm=employer_afm,
        branch_aa=branch_aa,
        employee_afm=employee_afm,
        work_date=work_date,
    )
    log_step(
        "Κατάσταση βάσης πριν την αποστολή",
        event="today_notification_db_snapshot",
        db_work_log_hour_from=db_snapshot.get("work_log_hour_from"),
        db_work_log_hour_to=db_snapshot.get("work_log_hour_to"),
        db_work_log_synced_at=db_snapshot.get("work_log_synced_at"),
        db_card_check_in=db_snapshot.get("card_check_in"),
        db_card_check_out=db_snapshot.get("card_check_out"),
        db_card_has_check_in=db_snapshot.get("card_has_check_in"),
        db_card_has_check_out=db_snapshot.get("card_has_check_out"),
        notify_input_hour_from=hf,
        notify_input_hour_to=ht,
    )
    recipients = list_deliverable_recipients(store_id)
    email_recipients = list_email_deliverable_recipients(store_id)
    log_step(
        "Βρέθηκαν λήπτες ειδοποίησης",
        telegram_recipients=len(recipients),
        email_recipients=len(email_recipients),
    )

    for rec in recipients:
        chat_id = str(rec.get("telegram_chat_id") or "").strip()
        if not chat_id:
            continue
        if is_snoozed(
            store_id=store_id,
            employee_afm=employee_afm,
            work_date_ergani=work_date,
            notify_kind=resolved_kind,
            recipient_id=int(rec["id"]),
        ):
            continue
        hit_url = None
        if (rec.get("notify_pin_hash") or "").strip():
            try:
                log_step(
                    "Δημιουργία token ενέργειας Telegram",
                    recipient_id=rec.get("id"),
                    recipient_name=rec.get("name"),
                    notification_channel="telegram",
                )
                token = create_today_alert_token(
                    recipient_id=int(rec["id"]),
                    store_id=store_id,
                    employee_afm=employee_afm,
                    eponymo=eponymo,
                    onoma=onoma,
                    work_date_ergani=work_date,
                    reference_date_iso=ref_iso,
                    notify_kind=resolved_kind,
                    hour_from=hour_from,
                    hour_to=hour_to,
                    schedule_hour_from=schedule_hour_from,
                )
                hit_url = build_today_hit_redirect_url(token)
            except Exception as ex:
                errors.append(f"{rec.get('name')}: token — {ex}")
        text = format_today_alert_notification(
            store_name=store_name,
            employee_afm=employee_afm,
            eponymo=eponymo,
            onoma=onoma,
            work_date=work_date,
            notify_kind=resolved_kind,
            hit_url=hit_url,
            has_pin=bool((rec.get("notify_pin_hash") or "").strip()),
        )
        try:
            log_step(
                "Αποστολή Telegram προς λήπτη",
                recipient_id=rec.get("id"),
                recipient_name=rec.get("name"),
                notification_channel="telegram",
            )
            send_telegram_message(chat_id, text)
            sent += 1
            log_notification(
                level="info",
                message=(
                    "Εστάλη ειδοποίηση Telegram: "
                    f"{employee_name or employee_afm} -> {rec.get('name') or rec.get('mobile')}"
                ),
                rec=rec,
                channel="telegram",
                extra={"telegram_chat_id": chat_id, "sent": True, **db_snapshot},
            )
            _auto_snooze_after_send(
                rec=rec,
                store_id=store_id,
                employee_afm=employee_afm,
                work_date=work_date,
                notify_kind=resolved_kind,
                auto_post_sync=auto_post_sync,
                log=log,
                employee_name=employee_name,
                kind_label=kind_label,
            )
        except Exception as ex:
            errors.append(f"{rec.get('name')}: {ex}")
            log_notification(
                level="error",
                message=(
                    "Αποτυχία ειδοποίησης Telegram: "
                    f"{employee_name or employee_afm} -> {rec.get('name') or rec.get('mobile')}"
                ),
                rec=rec,
                channel="telegram",
                extra={"telegram_chat_id": chat_id, "sent": False, "error": str(ex)},
            )

    for rec in email_recipients:
        email = str(rec.get("email") or "").strip()
        if not email:
            continue
        if is_snoozed(
            store_id=store_id,
            employee_afm=employee_afm,
            work_date_ergani=work_date,
            notify_kind=resolved_kind,
            recipient_id=int(rec["id"]),
        ):
            continue
        hit_url = None
        has_pin = bool((rec.get("notify_pin_hash") or "").strip())
        if has_pin:
            try:
                log_step(
                    "Δημιουργία token ενέργειας Email",
                    recipient_id=rec.get("id"),
                    recipient_name=rec.get("name"),
                    notification_channel="email",
                )
                token = create_today_alert_token(
                    recipient_id=int(rec["id"]),
                    store_id=store_id,
                    employee_afm=employee_afm,
                    eponymo=eponymo,
                    onoma=onoma,
                    work_date_ergani=work_date,
                    reference_date_iso=ref_iso,
                    notify_kind=resolved_kind,
                    hour_from=hour_from,
                    hour_to=hour_to,
                    schedule_hour_from=schedule_hour_from,
                )
                hit_url = build_today_hit_redirect_url(token)
            except Exception as ex:
                errors.append(f"Email {rec.get('name')}: token — {ex}")
        try:
            log_step(
                "Αποστολή Email προς λήπτη",
                recipient_id=rec.get("id"),
                recipient_name=rec.get("name"),
                recipient_email=email,
                notification_channel="email",
            )
            send_notification_email(
                email,
                f"erganiOS — {kind_label}",
                title=kind_label,
                preheader=f"{employee_name or employee_afm} · {work_date}",
                store_name=store_name,
                employee_name=employee_name,
                employee_afm=employee_afm,
                work_date=work_date,
                problem="Εντοπίστηκε σημερινή εκκρεμότητα κάρτας εργασίας.",
                details=[
                    ("Χτύπημα από", hour_from or "—"),
                    ("Χτύπημα έως", hour_to or "—"),
                    ("Ώρα ωραρίου", schedule_hour_from or "—"),
                    ("Ενέργεια", "Άνοιγμα ενέργειας" if hit_url else "Απαιτείται PIN λήπτη"),
                ],
                action_url=hit_url,
                action_label="Άνοιγμα ενέργειας",
                footer_note=(
                    "Το άνοιγμα της ενέργειας απαιτεί τον προσωπικό PIN του λήπτη."
                    if hit_url
                    else "Δεν δημιουργήθηκε σύνδεσμος επειδή δεν έχει οριστεί PIN για τον λήπτη."
                ),
            )
            sent += 1
            log_notification(
                level="info",
                message=(
                    "Εστάλη ειδοποίηση Email: "
                    f"{employee_name or employee_afm} -> {rec.get('name') or email}"
                ),
                rec=rec,
                channel="email",
                extra={"sent": True, **db_snapshot},
            )
            _auto_snooze_after_send(
                rec=rec,
                store_id=store_id,
                employee_afm=employee_afm,
                work_date=work_date,
                notify_kind=resolved_kind,
                auto_post_sync=auto_post_sync,
                log=log,
                employee_name=employee_name,
                kind_label=kind_label,
            )
        except EmailNotConfigured as ex:
            errors.append(f"Email {rec.get('name')}: {ex}")
            log_notification(
                level="error",
                message=(
                    "Αποτυχία ειδοποίησης Email: "
                    f"{employee_name or employee_afm} -> {rec.get('name') or email}"
                ),
                rec=rec,
                channel="email",
                extra={"sent": False, "error": str(ex)},
            )
        except Exception as ex:
            errors.append(f"Email {rec.get('name')}: {ex}")
            log_notification(
                level="error",
                message=(
                    "Αποτυχία ειδοποίησης Email: "
                    f"{employee_name or employee_afm} -> {rec.get('name') or email}"
                ),
                rec=rec,
                channel="email",
                extra={"sent": False, "error": str(ex)},
            )

    if auto_post_sync and sent > 0 and notify_auto_send_once(resolved_kind):
        mark_notify_sent(
            store_id=store_id,
            employee_afm=employee_afm,
            work_date_ergani=work_date,
            notify_kind=resolved_kind,
            sent_via="auto_post_sync",
        )

    return {
        "sent": sent,
        "total": len(recipients) + len(email_recipients),
        "errors": errors,
        "notify_kind": resolved_kind,
    }
