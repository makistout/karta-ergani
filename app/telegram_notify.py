"""Αποστολή μηνυμάτων μέσω Telegram Bot API."""

from __future__ import annotations

from typing import Any

import requests

from config import Config


class TelegramNotConfigured(Exception):
    pass


def _bot_token() -> str:
    token = (Config.TELEGRAM_BOT_TOKEN or "").strip()
    if not token:
        raise TelegramNotConfigured(
            "Λείπει TELEGRAM_BOT_TOKEN στο .env (BotFather → token)."
        )
    return token


def send_telegram_message(chat_id: str, text: str, *, parse_mode: str | None = None) -> dict[str, Any]:
    token = _bot_token()
    cid = str(chat_id or "").strip()
    if not cid:
        raise ValueError("Λείπει chat_id")
    body: dict[str, Any] = {"chat_id": cid, "text": str(text)[:4096]}
    if parse_mode:
        body["parse_mode"] = parse_mode
    resp = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json=body,
        timeout=30,
    )
    data = resp.json() if resp.content else {}
    if not resp.ok or not data.get("ok"):
        desc = data.get("description") if isinstance(data, dict) else resp.text
        raise RuntimeError(desc or f"Telegram HTTP {resp.status_code}")
    return data


def notify_store_recipients(
    store_id: int,
    text: str,
    *,
    only_with_chat: bool = True,
) -> dict[str, Any]:
    from app.repo_notify_recipients import list_deliverable_recipients, list_notify_recipients

    rows = (
        list_deliverable_recipients(store_id)
        if only_with_chat
        else list_notify_recipients(store_id)
    )
    sent = 0
    errors: list[str] = []
    for row in rows:
        chat_id = str(row.get("telegram_chat_id") or "").strip()
        if not chat_id:
            errors.append(f"{row.get('name')}: χωρίς Telegram ID")
            continue
        try:
            send_telegram_message(chat_id, text)
            sent += 1
        except Exception as ex:
            errors.append(f"{row.get('name')}: {ex}")
    return {"sent": sent, "total": len(rows), "errors": errors}


def format_missing_punch_notification(
    *,
    store_name: str,
    employee_afm: str,
    eponymo: str | None,
    onoma: str | None,
    work_date: str,
    hour_from: str | None,
    hour_to: str | None,
    retro_time: str | None = None,
    card_event: str | None = None,
    hit_url: str | None = None,
    punch_url: str | None = None,
    has_pin: bool = False,
) -> str:
    """Κείμενο ειδοποίησης τύπου 1 — ελλιπές χτύπημα παρελθόντος."""
    link = (hit_url or punch_url or "").strip()
    name = f"{(eponymo or '').strip()} {(onoma or '').strip()}".strip() or employee_afm
    hf = (hour_from or "").strip()
    ht = (hour_to or "").strip()
    event = (card_event or "").strip()
    if event == "check_in":
        defect = "ελλιπές χτύπημα εισόδου"
    elif event == "check_out":
        defect = "ελλιπές χτύπημα εξόδου"
    elif not hf and not ht:
        defect = "ελλιπή είσοδο και έξοδο"
    elif not hf:
        defect = "ελλιπές χτύπημα εισόδου"
    else:
        defect = "ελλιπές χτύπημα εξόδου"
    store = (store_name or "").strip()
    prefix = f"erganiOS — {store}\n" if store else "erganiOS\n"
    lines = [
        f"{prefix}Για τον εργαζόμενο {name} (ΑΦΜ {employee_afm}) "
        f"υπάρχει {defect} την {work_date}."
    ]
    rt = (retro_time or "").strip()
    if rt and event == "check_in":
        lines.append(f"Προτεινόμενη ώρα εισόδου (ψηφ. ωράριο): {rt}.")
    elif rt and event == "check_out":
        lines.append(f"Προτεινόμενη ώρα εξόδου (ψηφ. ωράριο): {rt}.")
    if link:
        lines.append(
            f"\nΆνοιγμα προγενέστερης καταχώρησης (απαιτείται ο προσωπικός PIN σας):\n{link}"
        )
    elif not has_pin:
        lines.append(
            "\nΓια σύνδεσμο με PIN, ορίστε PIN λήπτη στο κατάστημα."
        )
    return "\n".join(lines)


def format_today_alert_notification(
    *,
    store_name: str,
    employee_afm: str,
    eponymo: str | None,
    onoma: str | None,
    work_date: str,
    notify_kind: str,
    hit_url: str | None = None,
    has_pin: bool = False,
    wto_hour_from: str | None = None,
    wto_hour_to: str | None = None,
) -> str:
    """Κείμενο ειδοποίησης τύπου 2 — πρόβλημα τρέχουσας ημέρας."""
    from app.today_notify_logic import KIND_LABELS, WTO_DAILY_NOTIFY_KINDS

    link = (hit_url or "").strip()
    name = f"{(eponymo or '').strip()} {(onoma or '').strip()}".strip() or employee_afm
    kind = (notify_kind or "").strip()
    problem = KIND_LABELS.get(kind, "πρόβλημα στην πραγματική απασχόληση")
    store = (store_name or "").strip()
    prefix = f"erganiOS — {store}\n" if store else "erganiOS\n"
    lines = [
        f"{prefix}Υπάρχει πρόβλημα με τον εργαζόμενο {name} (ΑΦΜ {employee_afm}) "
        f"για σήμερα ({work_date}): {problem}.",
    ]
    if kind in WTO_DAILY_NOTIFY_KINDS:
        hf = (wto_hour_from or "").strip()
        ht = (wto_hour_to or "").strip()
        if hf:
            sched_line = f"Προτεινόμενο ωράριο: {hf}"
            if ht:
                sched_line += f" – {ht}"
            lines.append(sched_line)
    lines.extend(["", "Προχωρήστε σε ενέργεια:"])
    if link:
        lines.append(link)
    elif not has_pin:
        lines.append(
            "(Ορίστε PIN λήπτη στο κατάστημα για σύνδεσμο με επιλογές ενέργειας.)"
        )
    return "\n".join(lines)
