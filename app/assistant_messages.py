"""Shared assistant copy for UI and Telegram channels."""

from __future__ import annotations

from config import Config
from app.work_card_payload import FUTURE_EVENT_AT_ERROR


def ai_agent_disabled_message() -> str:
    phone = Config.AI_AGENT_CONTACT_PHONE or "ΧΧΧΧΧΧΧ"
    return (
        "Ο ΑΙ agent δεν είναι ενεργοποιημένος. "
        f"Καλέστε στο {phone} για να ενημερωθείτε για το κόστος ενεργοποίησης του."
    )


def future_card_punch_blocked_message() -> str:
    return FUTURE_EVENT_AT_ERROR
