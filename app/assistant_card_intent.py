"""Detect open/close card action from user text — safety net over LLM intent."""

from __future__ import annotations

import re
import unicodedata
from typing import Any

# Imperative / action phrases only — not «ανοιχτή κάρτα» (info query).
_CHECK_IN_RE = re.compile(
    r"(?:"
    r"\bανοιξ(?:ε|τε|ει|το|τον)\b|"
    r"\bopen\b|"
    r"\bcheck[\s-]?in\b|"
    r"\bclock[\s-]?in\b|"
    r"\bcheckin\b|"
    r"\bclockin\b|"
    r"\bεισοδ(?:ο|ος|ου)\b"
    r")",
    re.IGNORECASE,
)
_CHECK_OUT_RE = re.compile(
    r"(?:"
    r"\bκλεισ(?:ε|τε|ει|το|τον)\b|"
    r"\bclose\b|"
    r"\bcheck[\s-]?out\b|"
    r"\bclock[\s-]?out\b|"
    r"\bcheckout\b|"
    r"\bclockout\b|"
    r"\bεξοδ(?:ο|ος|ου)\b"
    r")",
    re.IGNORECASE,
)


def _fold(value: str) -> str:
    text = unicodedata.normalize("NFD", str(value or "").casefold())
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    return text.replace("ς", "σ")


def card_action_direction_from_text(text: str) -> str | None:
    """Return check_in, check_out, or None if ambiguous / not a card action."""
    folded = _fold(text)
    if not folded:
        return None
    has_in = bool(_CHECK_IN_RE.search(folded))
    has_out = bool(_CHECK_OUT_RE.search(folded))
    if has_in and not has_out:
        return "check_in"
    if has_out and not has_in:
        return "check_out"
    return None


def _card_intent_suffix(parsed: dict[str, Any], user_text: str, current_intent: str) -> str:
    if current_intent.endswith("_schedule"):
        return "_schedule"
    if current_intent.endswith("_retro"):
        return "_retro"
    time_value = str(parsed.get("time") or "").strip()
    if re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", time_value):
        return "_retro"
    folded = _fold(user_text)
    if any(token in folded for token in ("βασει ωραρι", "ωραριου", "schedule")):
        return "_schedule"
    return "_now"


def correct_card_intent_from_text(parsed: dict[str, Any], user_text: str) -> bool:
    """Align card_check_* intent with explicit open/close wording in user text."""
    direction = card_action_direction_from_text(user_text)
    if not direction:
        return False

    intent = str(parsed.get("intent") or "unknown")
    suffix = _card_intent_suffix(parsed, user_text, intent)
    target = f"card_{direction}{suffix}"

    if intent.startswith("card_check_"):
        current = "check_in" if "check_in" in intent else "check_out"
        if current == direction:
            return False
        parsed["intent"] = target
        return True

    if intent == "unknown":
        has_employee = bool(parsed.get("employee_afms") or parsed.get("employee_afm"))
        if has_employee:
            parsed["intent"] = target
            return True
    return False
