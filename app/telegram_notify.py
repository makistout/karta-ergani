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
    punch_url: str | None = None,
    has_pin: bool = False,
) -> str:
    """Κείμενο ειδοποίησης για ελλιπή είσοδο/έξοδο πραγματικής απασχόλησης."""
    name = f"{(eponymo or '').strip()} {(onoma or '').strip()}".strip() or employee_afm
    hf = (hour_from or "").strip()
    ht = (hour_to or "").strip()
    missing: list[str] = []
    if not hf:
        missing.append("είσοδο")
    if not ht:
        missing.append("έξοδο")
    if len(missing) >= 2:
        defect = "ελλιπή είσοδο και έξοδο"
        punch_label = "είσοδο/έξοδο"
    elif missing and missing[0] == "είσοδο":
        defect = "ελλιπή είσοδο"
        punch_label = "είσοδο"
    else:
        defect = "ελλιπή έξοδο"
        punch_label = "έξοδο"
    store = (store_name or "").strip()
    prefix = f"erganiOS — {store}\n" if store else "erganiOS\n"
    lines = [
        f"{prefix}Ο εργαζόμενος {name} (ΑΦΜ {employee_afm}) "
        f"έχει {defect} την {work_date}."
    ]
    rt = (retro_time or "").strip()
    if rt and card_event:
        lines.append(f"Θα έπρεπε να χτυπήσει κάρτα {punch_label} στις {rt}.")
    if punch_url:
        lines.append(
            f"\nΑυτόματο χτύπημα (απαιτείται ο προσωπικός PIN σας):\n{punch_url}"
        )
    elif has_pin is False and rt:
        lines.append(
            "\nΓια σύνδεσμο αυτόματου χτυπήματος, ορίστε PIN λήπτη στο κατάστημα."
        )
    return "\n".join(lines)
