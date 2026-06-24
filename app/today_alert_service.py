"""Ειδοποίηση τύπου 2 — τρέχουσα ημέρα: αποστολή, PIN, ενέργειες."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

from flask import session

from app import repo_store as repo
from app.notify_pin import verify_notify_pin
from app.repo_notify_recipients import (
    list_deliverable_recipients,
    list_email_deliverable_recipients,
    normalize_mobile,
)
from app.repo_today_alert import (
    create_snooze,
    create_today_alert_token,
    get_today_alert_token_row,
    get_today_alert_token_row_by_id,
    increment_today_alert_pin_attempts,
    is_notify_sent,
    is_snoozed,
    mark_notify_sent,
    mark_today_alert_action,
    mark_today_alert_pin_verified,
    today_alert_token_is_valid,
)
from app.repo_work_log import enrich_work_log_rows_with_schedule
from app.telegram_punch_service import (
    TELEGRAM_PUNCH_SESSION_KEY,
    _activate_store_session,
    _context_from_token_row,
    build_retro_hit_redirect_url,
)
from app.today_notify_logic import (
    KIND_LABELS,
    WTO_DAILY_NOTIFY_KINDS,
    card_action_for_today_kind,
    ergani_date_to_iso,
    notify_auto_send_once,
    resolve_today_notify_kind,
    today_leave_eligible,
    today_wto_daily_eligible,
)
from config import Config

TODAY_ALERT_SESSION_KEY = "today_alert_ctx"


def _context_from_today_row(row: dict[str, Any]) -> dict[str, Any]:
    name = f"{row.get('eponymo') or ''} {row.get('onoma') or ''}".strip()
    kind = str(row.get("notify_kind") or "").strip()
    return {
        "token_id": int(row["id"]),
        "store_id": int(row["store_id"]),
        "store_name": row.get("store_name"),
        "employee_afm": row.get("employee_afm"),
        "employee_name": name or row.get("employee_afm"),
        "eponymo": row.get("eponymo"),
        "onoma": row.get("onoma"),
        "work_date_ergani": row.get("work_date_ergani"),
        "reference_date_iso": row.get("reference_date_iso")
        or ergani_date_to_iso(str(row.get("work_date_ergani") or "")),
        "notify_kind": kind,
        "notify_kind_label": KIND_LABELS.get(kind, kind),
        "hour_from": row.get("hour_from"),
        "hour_to": row.get("hour_to"),
        "schedule_hour_from": row.get("schedule_hour_from"),
        "leave_eligible": today_leave_eligible(
            kind,
            schedule_hour_from=row.get("schedule_hour_from"),
            hour_from=row.get("hour_from"),
            hour_to=row.get("hour_to"),
        ),
        "wto_daily_eligible": today_wto_daily_eligible(kind),
        "wto_hour_from": (row.get("hour_from") or "").strip() or None,
        "wto_hour_to": (row.get("hour_to") or "").strip() or None,
        "wto_schedule_type": "ΕΡΓ",
    }


def _store_today_alert_session(row: dict[str, Any]) -> None:
    session[TODAY_ALERT_SESSION_KEY] = _context_from_today_row(row)


def clear_today_alert_session() -> None:
    session.pop(TODAY_ALERT_SESSION_KEY, None)


def get_today_action_context(*, token: str | None = None) -> tuple[dict[str, Any] | None, str | None]:
    ctx = session.get(TODAY_ALERT_SESSION_KEY)
    if isinstance(ctx, dict) and ctx.get("token_id"):
        return ctx, None
    t = (token or "").strip()
    if t:
        row = get_today_alert_token_row(t)
        ok, err = today_alert_token_is_valid(row)
        if not ok or not row:
            return None, err or "Μη έγκυρο token"
        if not row.get("pin_verified_at"):
            return None, (
                "Ανοίξτε τον σύνδεσμο από το Telegram και εισάγετε πρώτα τον PIN σας."
            )
        return _context_from_today_row(row), None
    return None, "Η συνεδρία έληξε — ανοίξτε ξανά τον σύνδεσμο από το Telegram."


def build_today_action_redirect_url(token: str | None = None) -> str:
    base = (Config.PUBLIC_BASE_URL or "").rstrip("/") or ""
    path = f"{base}/ui/today-action" if base else "/ui/today-action"
    t = (token or "").strip()
    if t:
        return f"{path}?t={quote(t, safe='')}"
    return path


def build_today_hit_redirect_url(token: str | None = None) -> str:
    base = (Config.PUBLIC_BASE_URL or "").rstrip("/") or ""
    path = f"{base}/ui/today-hit" if base else "/ui/today-hit"
    t = (token or "").strip()
    if t:
        return f"{path}?t={quote(t, safe='')}"
    return path


def today_hit_preview(token: str) -> tuple[dict[str, Any] | None, str | None]:
    row = get_today_alert_token_row(token)
    ok, err = today_alert_token_is_valid(row)
    if not ok:
        return None, err
    assert row is not None
    kind = str(row.get("notify_kind") or "").strip()
    name = f"{row.get('eponymo') or ''} {row.get('onoma') or ''}".strip()
    return {
        "store_name": row.get("store_name"),
        "employee_name": name or row.get("employee_afm"),
        "employee_afm": row.get("employee_afm"),
        "work_date": row.get("work_date_ergani"),
        "notify_kind": kind,
        "notify_kind_label": KIND_LABELS.get(kind, kind),
        "recipient_name": row.get("recipient_name"),
        "notification_kind": "today_alert",
        "wto_daily_eligible": today_wto_daily_eligible(kind),
        "wto_hour_from": (row.get("hour_from") or "").strip() or None,
        "wto_hour_to": (row.get("hour_to") or "").strip() or None,
    }, None


def confirm_today_hit_with_pin(token: str, pin: str) -> tuple[dict[str, Any], int]:
    row = get_today_alert_token_row(token)
    ok, err = today_alert_token_is_valid(row)
    if not ok or not row:
        return {"success": False, "error": err or "Μη έγκυρο token"}, 400

    if not verify_notify_pin(
        store_id=int(row["store_id"]),
        mobile=normalize_mobile(row.get("mobile")),
        pin=str(pin or "").strip(),
        pin_hash=row.get("notify_pin_hash"),
    ):
        attempts = increment_today_alert_pin_attempts(int(row["id"]))
        if attempts >= 5:
            return {"success": False, "error": "Λάθος PIN — ο σύνδεσμος κλειδώθηκε"}, 403
        return {"success": False, "error": "Λάθος PIN"}, 401

    cfg = repo.get_store_config(int(row["store_id"]))
    if not cfg:
        return {"success": False, "error": "Δεν βρέθηκε κατάστημα"}, 404

    _activate_store_session(cfg)
    mark_today_alert_pin_verified(int(row["id"]))
    _store_today_alert_session(row)
    return {
        "success": True,
        "redirect": build_today_action_redirect_url(token),
        "detail": "Επιλέξτε ενέργεια για τον εργαζόμενο.",
    }, 200


def snooze_today_alert(*, token: str | None = None) -> tuple[dict[str, Any], int]:
    from app.client_request import capture_client_context
    from app.office_auth import SESSION_USER
    from flask import session

    ctx, err = get_today_action_context(token=token)
    if err or not ctx:
        return {"success": False, "error": err or "Λήξη συνεδρίας"}, 401
    row = get_today_alert_token_row_by_id(int(ctx["token_id"]))
    if not row:
        return {"success": False, "error": "Μη έγκυρο token"}, 400

    office_user = str(session.get(SESSION_USER) or "").strip() or None
    recipient_name = str(row.get("recipient_name") or "").strip() or None
    recipient_mobile = str(row.get("mobile") or "").strip() or None
    client_ctx = capture_client_context(
        "today_snooze",
        extra={
            "recipient_id": row.get("recipient_id"),
            "recipient_name": recipient_name,
            "token_id": row.get("id"),
            "office_user": office_user,
            "employee_afm": row.get("employee_afm"),
            "notify_kind": row.get("notify_kind"),
        },
    )
    acted_by = recipient_name or office_user or "—"
    acted_via = "telegram" if row.get("recipient_id") else "office"

    create_snooze(
        store_id=int(row["store_id"]),
        recipient_id=int(row["recipient_id"]),
        employee_afm=str(row.get("employee_afm") or ""),
        work_date_ergani=str(row.get("work_date_ergani") or ""),
        notify_kind=str(row.get("notify_kind") or ""),
        acted_by_name=acted_by,
        acted_by_mobile=recipient_mobile,
        acted_via=acted_via,
        office_user=office_user,
        client_ip=client_ctx.get("client_ip"),
        client_device=client_ctx.get("client_device"),
    )
    mark_today_alert_action(int(row["id"]), "snooze")
    clear_today_alert_session()
    return {
        "success": True,
        "detail": "Δεν θα σταλεί ξανά ειδοποίηση για αυτή την περίπτωση σήμερα.",
    }, 200


def prepare_card_from_today_alert(*, token: str | None = None) -> tuple[dict[str, Any], int]:
    ctx, err = get_today_action_context(token=token)
    if err or not ctx:
        return {"success": False, "error": err or "Λήξη συνεδρίας"}, 401
    row = get_today_alert_token_row_by_id(int(ctx["token_id"]))
    if not row:
        return {"success": False, "error": "Μη έγκυρο token"}, 400

    kind = str(row.get("notify_kind") or "").strip()
    action = card_action_for_today_kind(
        kind,
        schedule_hour_from=str(row.get("schedule_hour_from") or ""),
        hour_from=str(row.get("hour_from") or ""),
    )
    retro_row = {
        **row,
        "card_event": action["card_event"],
        "retro_time": action.get("retro_time") or "",
        "reference_date_iso": row.get("reference_date_iso"),
        "work_date_ergani": row.get("work_date_ergani"),
    }
    session[TELEGRAM_PUNCH_SESSION_KEY] = _context_from_token_row(retro_row)
    mark_today_alert_action(int(row["id"]), "card")
    clear_today_alert_session()
    return {
        "success": True,
        "redirect": build_retro_hit_redirect_url(),
        "detail": "Μετάβαση στην καταχώρηση χτυπήματος κάρτας.",
    }, 200


def mark_today_alert_leave_done(*, token_id: int) -> None:
    mark_today_alert_action(int(token_id), "leave")
    clear_today_alert_session()


def submit_today_leave(
    *,
    leave_type: str,
    comments: str | None = None,
    token: str | None = None,
) -> tuple[dict[str, Any], int]:
    ctx, err = get_today_action_context(token=token)
    if err or not ctx:
        return {"success": False, "error": err or "Λήξη συνεδρίας"}, 401
    if not ctx.get("leave_eligible"):
        return {
            "success": False,
            "error": "Η καταχώριση άδειας δεν είναι διαθέσιμη για αυτή την περίπτωση.",
        }, 400

    from app.http_helpers import ensure_ergani_bearer, json_or_text, persist_safe, response_body_text
    from app.ergani_client import ErganiClient
    from app.leave_payload import SUBMISSION_CODE_WTO_LEAVE, build_wto_leave_payload
    from app.repo_card import insert_declaration, parse_ergani_submit_response
    from app.repo_entities import upsert_employee
    from app.work_card_payload import WorkCardPayloadError
    from app.db import cursor
    from app.routes_leave import _persist_leave_submit

    cfg = repo.get_store_config(int(ctx["store_id"]))
    if not cfg:
        return {"success": False, "error": "Δεν βρέθηκε κατάστημα"}, 404
    _activate_store_session(cfg)
    bearer = ensure_ergani_bearer(cfg)
    if not bearer:
        return {"success": False, "error": "Αποτυχία σύνδεσης Ergani API"}, 401

    emp_afm = str(ctx.get("employee_afm") or "").strip()
    ref_date = str(ctx.get("reference_date_iso") or "").strip()[:10]
    last = str(ctx.get("eponymo") or "").strip()
    first = str(ctx.get("onoma") or "").strip()
    if not emp_afm or not ref_date or not leave_type.strip():
        return {"success": False, "error": "Λείπουν στοιχεία άδειας"}, 400
    if not last or not first:
        return {"success": False, "error": "Λείπουν επώνυμο/όνομα εργαζομένου"}, 400

    try:
        payload = build_wto_leave_payload(
            branch_aa=str(cfg.get("branch_aa") or "0"),
            employee_afm=emp_afm,
            employee_last_name=last,
            employee_first_name=first,
            reference_date=ref_date,
            leave_type=leave_type.strip(),
            comments=comments,
        )
    except WorkCardPayloadError as ex:
        return {"success": False, "error": str(ex)}, 400

    client = ErganiClient(cfg.get("api_base_url"))
    resp = client.document_submit(SUBMISSION_CODE_WTO_LEAVE, payload, bearer)
    parsed = json_or_text(resp)
    protocol = submit_date = ergani_id = None
    if resp.ok and isinstance(parsed, list) and parsed:
        first_item = parsed[0]
        if isinstance(first_item, dict):
            protocol = first_item.get("protocol")
            submit_date = first_item.get("submitDate")
            raw_id = first_item.get("id")
            ergani_id = str(raw_id).strip() if raw_id is not None else None

    persist_safe(
        _persist_leave_submit,
        str(cfg["employer_afm"]),
        resp.status_code,
        resp.ok,
        payload,
        response_body_text(resp),
        protocol,
        submit_date,
        ergani_id,
    )
    if resp.ok:
        with cursor() as cur:
            upsert_employee(cur, emp_afm, last, first)
        mark_today_alert_leave_done(token_id=int(ctx["token_id"]))

    err_msg = None
    if not resp.ok and isinstance(parsed, dict):
        err_msg = str(parsed.get("message") or parsed.get("Message") or "").strip() or None

    return {
        "success": resp.ok,
        "protocol": protocol,
        "submit_date": submit_date,
        "error": err_msg,
    }, (200 if resp.ok else 502)


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


def mark_today_alert_wto_done(*, token_id: int) -> None:
    mark_today_alert_action(int(token_id), "wto_daily")
    clear_today_alert_session()


def submit_today_wto_daily(
    *,
    hour_from: str | None = None,
    hour_to: str | None = None,
    comments: str | None = None,
    token: str | None = None,
) -> tuple[dict[str, Any], int]:
    ctx, err = get_today_action_context(token=token)
    if err or not ctx:
        return {"success": False, "error": err or "Λήξη συνεδρίας"}, 401
    if not ctx.get("wto_daily_eligible"):
        return {
            "success": False,
            "error": "Η αλλαγή ωραρίου δεν είναι διαθέσιμη για αυτή την περίπτωση.",
        }, 400

    from app.http_helpers import ensure_ergani_bearer, json_or_text, persist_safe, response_body_text
    from app.ergani_client import ErganiClient
    from app.wto_daily_payload import SUBMISSION_CODE_WTO_DAILY, build_wto_daily_payload
    from app.work_card_payload import WorkCardPayloadError
    from app.routes_wto_daily import _persist_wto_daily_submit

    cfg = repo.get_store_config(int(ctx["store_id"]))
    if not cfg:
        return {"success": False, "error": "Δεν βρέθηκε κατάστημα"}, 404
    _activate_store_session(cfg)
    bearer = ensure_ergani_bearer(cfg)
    if not bearer:
        return {"success": False, "error": "Αποτυχία σύνδεσης Ergani API"}, 401

    emp_afm = str(ctx.get("employee_afm") or "").strip()
    ref_date = str(ctx.get("reference_date_iso") or "").strip()[:10]
    last = str(ctx.get("eponymo") or "").strip()
    first = str(ctx.get("onoma") or "").strip()
    hf = str(hour_from or ctx.get("wto_hour_from") or "").strip()
    ht = str(hour_to if hour_to is not None else ctx.get("wto_hour_to") or "").strip()
    if not emp_afm or not ref_date or not hf:
        return {"success": False, "error": "Λείπουν στοιχεία ωραρίου"}, 400
    if not last or not first:
        return {"success": False, "error": "Λείπουν επώνυμο/όνομα εργαζομένου"}, 400

    try:
        payload = build_wto_daily_payload(
            branch_aa=str(cfg.get("branch_aa") or "0"),
            employee_afm=emp_afm,
            employee_last_name=last,
            employee_first_name=first,
            reference_date=ref_date,
            schedule_type=str(ctx.get("wto_schedule_type") or "ΕΡΓ"),
            hour_from=hf,
            hour_to=ht or None,
            comments=comments,
        )
    except WorkCardPayloadError as ex:
        return {"success": False, "error": str(ex)}, 400

    client = ErganiClient(cfg.get("api_base_url"))
    resp = client.document_submit(SUBMISSION_CODE_WTO_DAILY, payload, bearer)
    parsed = json_or_text(resp)
    protocol = submit_date = ergani_id = None
    if resp.ok and isinstance(parsed, list) and parsed:
        first_item = parsed[0]
        if isinstance(first_item, dict):
            protocol = first_item.get("protocol")
            submit_date = first_item.get("submitDate")
            raw_id = first_item.get("id")
            ergani_id = str(raw_id).strip() if raw_id is not None else None

    persist_safe(
        _persist_wto_daily_submit,
        str(cfg["employer_afm"]),
        resp.status_code,
        resp.ok,
        payload,
        response_body_text(resp),
        protocol,
        submit_date,
        ergani_id,
    )
    if resp.ok:
        from app.db import cursor
        from app.repo_entities import upsert_employee

        with cursor() as cur:
            upsert_employee(cur, emp_afm, last, first)
        mark_today_alert_wto_done(token_id=int(ctx["token_id"]))

    err_msg = None
    if not resp.ok and isinstance(parsed, dict):
        err_msg = str(parsed.get("message") or parsed.get("Message") or "").strip() or None

    return {
        "success": resp.ok,
        "protocol": protocol,
        "submit_date": submit_date,
        "error": err_msg,
    }, (200 if resp.ok else 502)


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
