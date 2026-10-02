"""Αυτόματη αποστολή ορφανών χτυπημάτων — 10:00 για την προηγούμενη ημέρα."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Any

from app.date_util import format_date_for_ergani
from app.ergani_env import store_api_context
from app.karta_log import KartaLogger
from app.work_card_payload import norm_afm, tz_athens
from app.work_log_overnight import (
    ergani_next_day,
    is_exit_only_item,
    is_open_entry_item,
    merge_overnight_exits_across_days,
)
from app import repo_sync_log
from config import Config

OPERATION_ORPHAN_PUNCH_NOTIFY = "scheduled_orphan_punch_notify"
OPERATION_ORPHAN_PUNCH_MONTHLY_NOTIFY = "scheduled_orphan_punch_monthly_notify"
_OVERNIGHT_EXIT_BEFORE_MINUTES = 6 * 60
_GREEK_MONTH_GENITIVE = {
    1: "Ιανουαρίου",
    2: "Φεβρουαρίου",
    3: "Μαρτίου",
    4: "Απριλίου",
    5: "Μαΐου",
    6: "Ιουνίου",
    7: "Ιουλίου",
    8: "Αυγούστου",
    9: "Σεπτεμβρίου",
    10: "Οκτωβρίου",
    11: "Νοεμβρίου",
    12: "Δεκεμβρίου",
}


def should_run_orphan_punch_notify(
    cfg: dict[str, Any],
    *,
    now: datetime | None = None,
) -> tuple[bool, str, str]:
    """Επιστρέφει (τρέχει, ISO ημερομηνία στόχου=χθες, λόγος)."""
    from app.scheduled_sync import (
        _add_iso_days,
        _normalized_sync_time,
        _operation_run_exists,
    )

    if now is None:
        local_now = datetime.now(tz_athens())
    elif now.tzinfo is None:
        local_now = now.replace(tzinfo=tz_athens())
    else:
        local_now = now.astimezone(tz_athens())
    if not Config.KARTA_SCHEDULED_ORPHAN_PUNCH_NOTIFY_ENABLED:
        return False, "", "απενεργοποιημένο από ρύθμιση"
    base_date = local_now.date().isoformat()
    target_iso = _add_iso_days(base_date, -1)
    run_time = _normalized_sync_time(
        Config.KARTA_SCHEDULED_ORPHAN_PUNCH_NOTIFY_TIME,
        default="10:00",
    )
    if local_now.strftime("%H:%M") < run_time:
        return False, target_iso, f"αναμονή μέχρι {run_time}"
    if not repo_sync_log.tables_available():
        return False, target_iso, "λείπουν πίνακες sync log"
    if _operation_run_exists(
        OPERATION_ORPHAN_PUNCH_NOTIFY,
        int(cfg["id"]),
        base_date,
    ):
        return False, target_iso, "έχει ήδη εκτελεστεί σήμερα"
    return True, target_iso, "έτοιμο"


def _local_now(now: datetime | None) -> datetime:
    if now is None:
        return datetime.now(tz_athens())
    if now.tzinfo is None:
        return now.replace(tzinfo=tz_athens())
    return now.astimezone(tz_athens())


def previous_calendar_month(*, now: datetime | None = None) -> tuple[int, int]:
    first = _local_now(now).date().replace(day=1)
    prev = first - timedelta(days=1)
    return prev.year, prev.month


def greek_month_period_label(year: int, month: int) -> str:
    return f"{_GREEK_MONTH_GENITIVE.get(int(month), str(month))} {int(year)}"


def should_run_orphan_punch_monthly_notify(
    cfg: dict[str, Any],
    *,
    now: datetime | None = None,
) -> tuple[bool, str, str]:
    """Επιστρέφει (τρέχει, YYYY-MM προηγούμενου μήνα, λόγος). Μόνο την 1η."""
    from app.scheduled_sync import _normalized_sync_time, _operation_run_exists

    local_now = _local_now(now)
    year, month = previous_calendar_month(now=local_now)
    period = f"{year:04d}-{month:02d}"
    if not Config.KARTA_SCHEDULED_ORPHAN_PUNCH_MONTHLY_NOTIFY_ENABLED:
        return False, period, "απενεργοποιημένο από ρύθμιση"
    if local_now.day != 1:
        return False, period, "μόνο την 1η του μήνα"
    run_time = _normalized_sync_time(
        Config.KARTA_SCHEDULED_ORPHAN_PUNCH_MONTHLY_NOTIFY_TIME,
        default="10:00",
    )
    if local_now.strftime("%H:%M") < run_time:
        return False, period, f"αναμονή μέχρι {run_time}"
    if not repo_sync_log.tables_available():
        return False, period, "λείπουν πίνακες sync log"
    if _operation_run_exists(
        OPERATION_ORPHAN_PUNCH_MONTHLY_NOTIFY,
        int(cfg["id"]),
        local_now.date().isoformat(),
    ):
        return False, period, "έχει ήδη εκτελεστεί σήμερα"
    return True, period, "έτοιμο"


def _employee_display_name(row: dict[str, Any]) -> str:
    name = f"{(row.get('eponymo') or '').strip()} {(row.get('onoma') or '').strip()}".strip()
    return name or str(row.get("employee_afm") or row.get("afm") or "—")


def _hm(value: Any) -> str:
    text = str(value or "").strip().rstrip("*")
    return text[:5] if text else "—"


def _clock_minutes(value: Any) -> int | None:
    text = _hm(value)
    if len(text) < 4 or ":" not in text:
        return None
    try:
        hours, minutes = text.split(":", 1)
        return int(hours) * 60 + int(minutes)
    except ValueError:
        return None


def _is_overnight_clock(value: Any) -> bool:
    minutes = _clock_minutes(value)
    return minutes is not None and minutes < _OVERNIGHT_EXIT_BEFORE_MINUTES


def collect_orphan_punches_for_date(
    cfg: dict[str, Any],
    *,
    date_iso: str,
) -> list[dict[str, Any]]:
    """Ορφανά ζεύγη χθες + έξοδοι μετά τα μεσάνυχτα που ανήκουν στη χθεσινή μέρα."""
    from app.repo_work_log_core import list_work_log_for_range

    ctx = store_api_context(cfg)
    target = format_date_for_ergani(date_iso)
    next_day = ergani_next_day(target)
    rows = list_work_log_for_range(
        str(ctx.get("employer_afm") or ""),
        str(ctx.get("branch_aa") or "0"),
        [target, next_day],
    )
    by_day: dict[str, list[dict[str, Any]]] = {target: [], next_day: []}
    for row in rows:
        wd = str(row.get("work_date") or "").strip()
        if wd in by_day:
            by_day[wd].append(dict(row))
    merged = merge_overnight_exits_across_days(by_day)
    hits: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()

    def add_hit(row: dict[str, Any], *, kind: str, label: str, work_date: str) -> None:
        afm = norm_afm(str(row.get("employee_afm") or ""))
        if not afm:
            return
        key = (afm, kind, label)
        if key in seen:
            return
        seen.add(key)
        hits.append({
            "employee_afm": afm,
            "name": _employee_display_name(row),
            "kind": kind,
            "label": label,
            "work_date": work_date,
        })

    for row in merged.get(target) or []:
        if is_open_entry_item(row):
            add_hit(
                row,
                kind="open_entry",
                label=f"είσοδος {_hm(row.get('hour_from'))} χωρίς έξοδο",
                work_date=target,
            )
        elif is_exit_only_item(row):
            add_hit(
                row,
                kind="exit_only",
                label=f"έξοδος {_hm(row.get('hour_to'))} χωρίς είσοδο",
                work_date=target,
            )

    for row in merged.get(next_day) or []:
        if not is_exit_only_item(row) or not _is_overnight_clock(row.get("hour_to")):
            continue
        add_hit(
            row,
            kind="overnight_exit",
            label=(
                f"έξοδος {_hm(row.get('hour_to'))} χωρίς είσοδο "
                f"(μετά τα μεσάνυχτα)"
            ),
            work_date=next_day,
        )

    hits.sort(key=lambda item: (str(item.get("name") or "").upper(), item.get("kind") or ""))
    return hits


def format_orphan_punch_digest(
    *,
    store_name: str,
    work_date_ergani: str,
    hits: list[dict[str, Any]],
) -> str:
    store = (store_name or "").strip() or "κατάστημα"
    lines = [
        f"erganiOS — {store}",
        f"Ορφανά χτυπήματα χθες ({work_date_ergani}):",
        "",
    ]
    for hit in hits:
        name = hit.get("name") or hit.get("employee_afm")
        afm = hit.get("employee_afm") or "—"
        label = str(hit.get("label") or "ορφανό χτύπημα")
        lines.append(f"• {name} (ΑΦΜ {afm}): {label}")
    return "\n".join(lines)


def collect_monthly_orphan_repeaters(
    cfg: dict[str, Any],
    *,
    year: int,
    month: int,
    min_count: int | None = None,
) -> list[dict[str, Any]]:
    """Εργαζόμενοι με τουλάχιστον min_count εκκρεμή ορφανά στον μήνα."""
    from app.repo_entities import list_employees_for_employer
    from app.repo_work_log import count_incomplete_punches_by_employee_for_month

    threshold = int(
        min_count
        if min_count is not None
        else Config.KARTA_SCHEDULED_ORPHAN_PUNCH_MONTHLY_NOTIFY_MIN
    )
    ctx = store_api_context(cfg)
    employer_afm = str(ctx.get("employer_afm") or "")
    branch_aa = str(ctx.get("branch_aa") or "0")
    counts = count_incomplete_punches_by_employee_for_month(
        employer_afm,
        branch_aa,
        year=int(year),
        month=int(month),
        store_id=int(cfg["id"]),
    )
    names: dict[str, str] = {}
    try:
        for row in list_employees_for_employer(
            employer_afm, branch_aa=branch_aa, active_only=False, limit=5000
        ):
            afm = norm_afm(str(row.get("afm") or ""))
            if afm:
                names[afm] = _employee_display_name(row)
    except Exception:
        names = {}

    hits: list[dict[str, Any]] = []
    for raw_afm, count in (counts or {}).items():
        afm = norm_afm(str(raw_afm or ""))
        total = int(count or 0)
        if not afm or total < threshold:
            continue
        name = names.get(afm) or afm
        hits.append({
            "employee_afm": afm,
            "name": name,
            "count": total,
            "label": f"{total} ορφανά χτυπήματα",
        })
    hits.sort(key=lambda item: (-int(item["count"]), str(item["name"] or "").upper()))
    return hits


def format_monthly_orphan_digest(
    *,
    store_name: str,
    period_label: str,
    min_count: int,
    hits: list[dict[str, Any]],
) -> str:
    store = (store_name or "").strip() or "κατάστημα"
    lines = [
        f"erganiOS — {store}",
        f"Εργαζόμενοι με {min_count}+ ορφανά χτυπήματα τον {period_label}:",
        "",
    ]
    for hit in hits:
        name = hit.get("name") or hit.get("employee_afm")
        afm = hit.get("employee_afm") or "—"
        count = int(hit.get("count") or 0)
        lines.append(f"• {name} (ΑΦΜ {afm}): {count} ορφανά")
    return "\n".join(lines)


def _send_digest_to_recipients(
    *,
    store_id: int,
    store_name: str,
    work_date_ergani: str,
    text: str,
    hits: list[dict[str, Any]],
    email_subject: str = "erganiOS — Ορφανά χτυπήματα χθες",
    email_title: str = "Ορφανά χτυπήματα χθες",
    problem: str | None = None,
    footer_note: str | None = None,
    preheader: str | None = None,
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

    detail_rows = [
        (f"{hit.get('name')} ({hit.get('employee_afm')})", str(hit.get("label") or ""))
        for hit in hits
    ]

    for rec in email_recipients:
        email = str(rec.get("email") or "").strip()
        if not email:
            continue
        try:
            send_notification_email(
                email,
                email_subject,
                title=email_title,
                preheader=preheader or f"{store_name} · {work_date_ergani}",
                store_name=store_name,
                employee_name="—",
                employee_afm=None,
                work_date=work_date_ergani,
                problem=problem or (
                    f"Βρέθηκαν {len(hits)} ορφανά χτυπήματα "
                    f"για χθες ({work_date_ergani})."
                ),
                details=detail_rows[:40],
                footer_note=footer_note or (
                    "Η ειδοποίηση στέλνεται αυτόματα στις 10:00 για την προηγούμενη ημέρα, "
                    "μαζί με εξόδους μετά τα μεσάνυχτα που ανήκουν σε εκείνη τη βάρδια."
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


def run_orphan_punch_notify_for_store(
    cfg: dict[str, Any],
    *,
    target_date_iso: str,
    parent_run_id: str | None = None,
) -> dict[str, Any]:
    sid = int(cfg["id"])
    name = str(cfg.get("name") or sid)
    target = str(target_date_iso).strip()[:10]
    work_date_ergani = format_date_for_ergani(target)
    _ = parent_run_id
    log = KartaLogger(
        OPERATION_ORPHAN_PUNCH_NOTIFY,
        store_id=sid,
        store_name=name,
        run_id=str(uuid.uuid4()),
        extra={"target_date": target},
    )
    try:
        hits = collect_orphan_punches_for_date(cfg, date_iso=target)
        if not hits:
            detail = f"Κανένα ορφανό χτύπημα για {work_date_ergani}"
            log.info(detail, target_date=target, hits=0)
            repo_sync_log.finish_run(
                log.run_id,
                status="done",
                message=detail,
                result={
                    "success": True,
                    "skipped": True,
                    "reason": "no_orphans",
                    "target_date": target,
                    "hits": 0,
                    "sent": 0,
                },
            )
            return {
                "success": True,
                "skipped": True,
                "reason": "no_orphans",
                "target_date": target,
                "hits": 0,
                "sent": 0,
            }

        text = format_orphan_punch_digest(
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
            f"Ορφανά χθες {work_date_ergani}: {len(hits)} χτυπήματα, "
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
        log.error(f"Σφάλμα αποστολής ορφανών χτυπημάτων: {err}")
        repo_sync_log.finish_run(
            log.run_id,
            status="error",
            message=err,
            result={"success": False, "target_date": target, "error": err},
        )
        return {"success": False, "target_date": target, "error": err}


def run_orphan_punch_monthly_notify_for_store(
    cfg: dict[str, Any],
    *,
    period: str,
    parent_run_id: str | None = None,
) -> dict[str, Any]:
    sid = int(cfg["id"])
    name = str(cfg.get("name") or sid)
    raw = str(period or "").strip()
    try:
        year_s, month_s = raw.split("-", 1)
        year, month = int(year_s), int(month_s)
    except ValueError:
        year, month = previous_calendar_month()
        raw = f"{year:04d}-{month:02d}"
    period_label = greek_month_period_label(year, month)
    min_count = int(Config.KARTA_SCHEDULED_ORPHAN_PUNCH_MONTHLY_NOTIFY_MIN)
    _ = parent_run_id
    log = KartaLogger(
        OPERATION_ORPHAN_PUNCH_MONTHLY_NOTIFY,
        store_id=sid,
        store_name=name,
        run_id=str(uuid.uuid4()),
        extra={"period": raw, "min_count": min_count},
    )
    try:
        hits = collect_monthly_orphan_repeaters(
            cfg, year=year, month=month, min_count=min_count
        )
        if not hits:
            detail = (
                f"Κανένας με {min_count}+ ορφανά τον {period_label}"
            )
            log.info(detail, period=raw, hits=0)
            repo_sync_log.finish_run(
                log.run_id,
                status="done",
                message=detail,
                result={
                    "success": True,
                    "skipped": True,
                    "reason": "no_repeaters",
                    "period": raw,
                    "hits": 0,
                    "sent": 0,
                },
            )
            return {
                "success": True,
                "skipped": True,
                "reason": "no_repeaters",
                "period": raw,
                "hits": 0,
                "sent": 0,
            }

        text = format_monthly_orphan_digest(
            store_name=name,
            period_label=period_label,
            min_count=min_count,
            hits=hits,
        )
        delivery = _send_digest_to_recipients(
            store_id=sid,
            store_name=name,
            work_date_ergani=period_label,
            text=text,
            hits=hits,
            email_subject=f"erganiOS — Ορφανά χτυπήματα {period_label}",
            email_title=f"Ορφανά χτυπήματα {period_label}",
            preheader=f"{name} · {min_count}+ ορφανά",
            problem=(
                f"{len(hits)} εργαζόμενοι έχουν από {min_count} ορφανά χτυπήματα "
                f"και πάνω τον {period_label}."
            ),
            footer_note=(
                "Η ειδοποίηση στέλνεται αυτόματα την 1η του μήνα για τον μήνα "
                "που πέρασε. Μετρά εκκρεμή ορφανά (χωρίς κλείσιμο από δήλωση "
                "κάρτας / Telegram)."
            ),
        )
        detail = (
            f"Ορφανά {period_label}: {len(hits)} εργαζόμενοι με {min_count}+, "
            f"αποστολές {delivery.get('sent', 0)}"
        )
        log.info(
            detail,
            period=raw,
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
                "period": raw,
                "hits": len(hits),
                "delivery": delivery,
            },
        )
        return {
            "success": True,
            "period": raw,
            "hits": len(hits),
            "sent": int(delivery.get("sent") or 0),
            "delivery": delivery,
        }
    except Exception as ex:
        err = str(ex)
        log.error(f"Σφάλμα μηνιαίας αποστολής ορφανών χτυπημάτων: {err}")
        repo_sync_log.finish_run(
            log.run_id,
            status="error",
            message=err,
            result={"success": False, "period": raw, "error": err},
        )
        return {"success": False, "period": raw, "error": err}
