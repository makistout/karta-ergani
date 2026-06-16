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
