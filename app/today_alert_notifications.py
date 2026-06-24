"""Telegram/Email notification senders for today alerts."""

from __future__ import annotations

from typing import Any

from app.repo_notify_recipients import (
    list_deliverable_recipients,
    list_email_deliverable_recipients,
)
from app.repo_today_alert import (
    create_today_alert_token,
    is_notify_sent,
    is_snoozed,
    mark_notify_sent,
)
from app.repo_work_log import enrich_work_log_rows_with_schedule
from app.today_notify_logic import (
    KIND_LABELS,
    WTO_DAILY_NOTIFY_KINDS,
    ergani_date_to_iso,
    notify_auto_send_once,
    resolve_today_notify_kind,
)
from app.public_urls import ui_public_url


def build_today_hit_redirect_url(token: str | None = None) -> str:
    return ui_public_url("/ui/today-hit", token=token)


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

    if is_snoozed(
        store_id=store_id,
        employee_afm=employee_afm,
        work_date_ergani=work_date,
        notify_kind=kind,
    ):
        return {
            "sent": 0,
            "total": 0,
            "errors": [],
            "skipped": "snoozed",
        }

    recipients = list_deliverable_recipients(store_id)
    email_recipients = list_email_deliverable_recipients(store_id)
    sent = 0
    errors: list[str] = []
    ref_iso = ergani_date_to_iso(work_date)

    for rec in recipients:
        chat_id = str(rec.get("telegram_chat_id") or "").strip()
        if not chat_id:
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
) -> dict[str, Any]:
    from app.email_notify import EmailNotConfigured, send_notification_email
    from app.telegram_notify import (
        TelegramNotConfigured,
        format_today_alert_notification,
        send_telegram_message,
    )

    row: dict[str, Any] = {
        "employee_afm": employee_afm,
        "work_date": work_date,
        "hour_from": hour_from,
        "hour_to": hour_to,
        "eponymo": eponymo,
        "onoma": onoma,
    }
    enrich_work_log_rows_with_schedule(
        [row], employer_afm, branch_aa, [work_date]
    )
    sched = row.get("schedule") if isinstance(row.get("schedule"), dict) else {}
    schedule_hour_from = str((sched or {}).get("hour_from") or "").strip() or None
    schedule_hour_to = str((sched or {}).get("hour_to") or "").strip() or None

    resolved_kind = resolve_today_notify_kind(row)
    if not resolved_kind:
        return {
            "sent": 0,
            "total": 0,
            "errors": [],
            "skipped": "no_alert",
        }
    if notify_kind and notify_kind.strip() != resolved_kind:
        return {
            "sent": 0,
            "total": 0,
            "errors": [],
            "skipped": "kind_mismatch",
        }
    if is_snoozed(
        store_id=store_id,
        employee_afm=employee_afm,
        work_date_ergani=work_date,
        notify_kind=resolved_kind,
    ):
        return {
            "sent": 0,
            "total": 0,
            "errors": [],
            "skipped": "snoozed",
        }
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
        return {
            "sent": 0,
            "total": 0,
            "errors": [],
            "skipped": "already_sent",
        }

    recipients = list_deliverable_recipients(store_id)
    email_recipients = list_email_deliverable_recipients(store_id)
    sent = 0
    errors: list[str] = []
    ref_iso = ergani_date_to_iso(work_date)

    for rec in recipients:
        chat_id = str(rec.get("telegram_chat_id") or "").strip()
        if not chat_id:
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
            send_telegram_message(chat_id, text)
            sent += 1
        except Exception as ex:
            errors.append(f"{rec.get('name')}: {ex}")

    employee_name = f"{(eponymo or '').strip()} {(onoma or '').strip()}".strip()
    kind_label = KIND_LABELS.get(resolved_kind, resolved_kind)
    for rec in email_recipients:
        email = str(rec.get("email") or "").strip()
        if not email:
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
                    notify_kind=resolved_kind,
                    hour_from=hour_from,
                    hour_to=hour_to,
                    schedule_hour_from=schedule_hour_from,
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
        except EmailNotConfigured as ex:
            errors.append(f"Email {rec.get('name')}: {ex}")
        except Exception as ex:
            errors.append(f"Email {rec.get('name')}: {ex}")

    if auto_post_sync and notify_auto_send_once(resolved_kind) and sent > 0:
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
