"""Gemini intent extraction for authorized Telegram replies (dry-run only)."""

from __future__ import annotations

import json
import re
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

import requests

from app.repo_entities import list_employees_for_employer
from config import Config

ALLOWED_INTENTS = {
    "card_check_in_now",
    "card_check_out_now",
    "card_check_in_retro",
    "card_check_out_retro",
    "schedule_change",
    "rest_day",
    "leave",
    "unknown",
}


def _is_iso_date(value: str) -> bool:
    """Require a real calendar date, not just a YYYY-MM-DD-shaped value."""
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return False
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True

_SCHEMA = {
    "type": "object",
    "properties": {
        "intent": {"type": "string", "enum": sorted(ALLOWED_INTENTS)},
        "store_id": {"type": ["integer", "null"]},
        "employee_afm": {"type": ["string", "null"]},
        "employee_reference": {"type": ["string", "null"]},
        "date": {"type": ["string", "null"]},
        "time": {"type": ["string", "null"]},
        "hour_from": {"type": ["string", "null"]},
        "hour_to": {"type": ["string", "null"]},
        "leave_type": {"type": ["string", "null"]},
        "confidence": {"type": "number"},
        "clarification_question": {"type": ["string", "null"]},
    },
    "required": ["intent", "confidence"],
}


def _employee_catalog(contexts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[tuple[int, str]] = set()
    for ctx in contexts:
        store_id = int(ctx["store_id"])
        employees = list_employees_for_employer(
            str(ctx.get("employer_afm") or ""),
            str(ctx.get("branch_aa") or "0"),
            limit=1000,
        )
        for emp in employees:
            afm = str(emp.get("afm") or "").strip()
            key = (store_id, afm)
            if not afm or key in seen:
                continue
            seen.add(key)
            result.append({
                "store_id": store_id,
                "afm": afm,
                "name": f"{emp.get('eponymo') or ''} {emp.get('onoma') or ''}".strip(),
            })
    return result[:1500]


def _extract_json(data: dict[str, Any]) -> dict[str, Any]:
    candidates = data.get("candidates") or []
    parts = (((candidates[0] if candidates else {}).get("content") or {}).get("parts") or [])
    text = "".join(str(part.get("text") or "") for part in parts if isinstance(part, dict)).strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.I)
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise ValueError("Το Gemini δεν επέστρεψε JSON object")
    return parsed


def parse_command(
    *, text: str, contexts: list[dict[str, Any]], reply_context: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if not Config.GEMINI_API_KEY:
        raise RuntimeError("Δεν έχει ρυθμιστεί GEMINI_API_KEY")
    now = datetime.now(ZoneInfo("Europe/Athens"))
    employees = _employee_catalog(contexts)
    stores = [
        {"id": int(c["store_id"]), "name": str(c.get("store_name") or "")}
        for c in contexts
    ]
    prompt = {
        "role": "Μετατροπή ελληνικού μηνύματος σε δομημένη draft εντολή εργασίας.",
        "rules": [
            "Επίλεξε μόνο store_id και employee_afm που υπάρχουν στους δοσμένους καταλόγους.",
            "Το τώρα σημαίνει την τρέχουσα ώρα Europe/Athens.",
            "Για πριν/στις ΧΧ:ΧΧ χρησιμοποίησε retro intent.",
            "Για αλλαγή ωραρίου δώσε hour_from και hour_to.",
            "Για ρεπό χρησιμοποίησε rest_day. Για άδεια χρησιμοποίησε leave.",
            "Αν κάτι είναι ασαφές επέστρεψε unknown και σύντομη clarification_question στα ελληνικά.",
            "Μην επινοήσεις εργαζόμενο, ΑΦΜ, κατάστημα, ημερομηνία ή ώρα.",
        ],
        "now": now.isoformat(timespec="minutes"),
        "message": str(text)[:4096],
        "reply_context": reply_context or {},
        "allowed_stores": stores,
        "allowed_employees": employees,
    }
    response = requests.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{Config.GEMINI_MODEL}:generateContent",
        headers={"x-goog-api-key": Config.GEMINI_API_KEY, "Content-Type": "application/json"},
        json={
            "contents": [{"role": "user", "parts": [{"text": json.dumps(prompt, ensure_ascii=False)}]}],
            "generationConfig": {
                "temperature": 0,
                "responseMimeType": "application/json",
                "responseJsonSchema": _SCHEMA,
            },
        },
        timeout=20,
    )
    if not response.ok:
        raise RuntimeError(f"Gemini HTTP {response.status_code}: {response.text[:500]}")
    return _extract_json(response.json()), employees


def validate_and_describe(
    parsed: dict[str, Any], *, contexts: list[dict[str, Any]], employees: list[dict[str, Any]],
) -> tuple[str, dict[str, Any], str]:
    errors: list[str] = []
    intent = str(parsed.get("intent") or "unknown")
    if intent not in ALLOWED_INTENTS:
        intent = "unknown"
        parsed["intent"] = intent
        errors.append("Μη υποστηριζόμενη εντολή")

    allowed_store_ids = {int(c["store_id"]) for c in contexts}
    store_id = parsed.get("store_id")
    if store_id is None and len(allowed_store_ids) == 1:
        store_id = next(iter(allowed_store_ids))
        parsed["store_id"] = store_id
    try:
        store_id = int(store_id) if store_id is not None else None
    except (TypeError, ValueError):
        store_id = None
    if store_id not in allowed_store_ids:
        errors.append("Δεν προσδιορίστηκε μοναδικό επιτρεπόμενο κατάστημα")
    else:
        parsed["store_id"] = store_id

    afm = str(parsed.get("employee_afm") or "").strip()
    match = next((e for e in employees if e["store_id"] == store_id and e["afm"] == afm), None)
    if intent != "unknown" and not match:
        errors.append("Δεν προσδιορίστηκε μοναδικός εργαζόμενος του καταστήματος")

    date = str(parsed.get("date") or "").strip()
    if intent != "unknown" and not _is_iso_date(date):
        errors.append("Δεν προσδιορίστηκε έγκυρη ημερομηνία")
    time_value = str(parsed.get("time") or "").strip()
    if intent in {"card_check_in_retro", "card_check_out_retro"} and not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", time_value):
        errors.append("Δεν προσδιορίστηκε έγκυρη ώρα προγενέστερου χτυπήματος")
    if intent == "schedule_change":
        for field in ("hour_from", "hour_to"):
            if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", str(parsed.get(field) or "")):
                errors.append("Το νέο ωράριο χρειάζεται έγκυρη έναρξη και λήξη")
                break
    if intent == "leave" and not str(parsed.get("leave_type") or "").strip():
        errors.append("Η άδεια χρειάζεται συγκεκριμένο τύπο")
    if intent == "unknown":
        errors.append(str(parsed.get("clarification_question") or "Δεν αναγνωρίστηκε υποστηριζόμενη εντολή"))

    validation = {"valid": not errors, "errors": errors, "execution_enabled": False}
    status = "draft" if not errors else "needs_clarification"
    name = str(match.get("name") if match else parsed.get("employee_reference") or afm or "εργαζόμενος")
    store_name = next((str(c.get("store_name") or c["store_id"]) for c in contexts if int(c["store_id"]) == store_id), "—")
    labels = {
        "card_check_in_now": "Άνοιγμα κάρτας τώρα",
        "card_check_out_now": "Κλείσιμο κάρτας τώρα",
        "card_check_in_retro": f"Άνοιγμα κάρτας στις {time_value}",
        "card_check_out_retro": f"Κλείσιμο κάρτας στις {time_value}",
        "schedule_change": f"Αλλαγή ωραρίου σε {parsed.get('hour_from') or '—'}–{parsed.get('hour_to') or '—'}",
        "rest_day": "Δήλωση ρεπό",
        "leave": f"Δήλωση άδειας ({parsed.get('leave_type') or 'τύπος προς διευκρίνιση'})",
        "unknown": "Μη αναγνωρισμένη εντολή",
    }
    proposed = f"{labels[intent]} · {name} · {date or '—'} · {store_name}"
    return status, validation, proposed
