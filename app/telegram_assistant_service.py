"""Gemini intent extraction for authorized Telegram replies (dry-run only)."""

from __future__ import annotations

import json
import re
import time
import unicodedata
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

import requests

from app.repo_entities import list_active_employees_for_store
from config import Config

from app.assistant_home_context import build_today_home_context
from app.assistant_messages import future_card_punch_blocked_message

ALLOWED_INTENTS = {
    "card_check_in_now",
    "card_check_out_now",
    "card_check_in_retro",
    "card_check_out_retro",
    "card_check_in_schedule",
    "card_check_out_schedule",
    "schedule_change",
    "rest_day",
    "leave",
    "today_info",
    "unknown",
}
_INFO_INTENTS = {"today_info"}

_GEMINI_RETRY_STATUSES = {429, 500, 502, 503, 504}
_GEMINI_FALLBACK_ATTEMPTS = 2


def _is_iso_date(value: str) -> bool:
    """Require a real calendar date, not just a YYYY-MM-DD-shaped value."""
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return False
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True

_COMMAND_SCHEMA = {
    "type": "object",
    "properties": {
        "intent": {"type": "string", "enum": sorted(ALLOWED_INTENTS)},
        "store_id": {"type": ["integer", "null"]},
        "employee_afms": {"type": "array", "items": {"type": "string"}},
        "employee_references": {"type": "array", "items": {"type": "string"}},
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
    "required": ["intent", "employee_afms", "employee_references", "confidence"],
}

_SCHEMA = {
    "type": "object",
    "properties": {
        "commands": {"type": "array", "items": _COMMAND_SCHEMA},
    },
    "required": ["commands"],
}


def _employee_catalog(contexts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[tuple[int, str]] = set()
    for ctx in contexts:
        store_id = int(ctx["store_id"])
        employees = list_active_employees_for_store(
            str(ctx.get("employer_afm") or ""),
            str(ctx.get("branch_aa") or "0"),
            limit=1000,
        )
        for emp in employees:
            if emp.get("active") in (False, 0, "0"):
                continue
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
    commands = parsed.get("commands")
    if isinstance(commands, list):
        valid_commands = [command for command in commands if isinstance(command, dict)]
        if len(valid_commands) == 1:
            return valid_commands[0]
        parsed["commands"] = valid_commands
    return parsed


def parse_command(
    *, text: str, contexts: list[dict[str, Any]], reply_context: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    if not Config.GEMINI_API_KEY:
        raise RuntimeError("Δεν έχει ρυθμιστεί GEMINI_API_KEY")
    now = datetime.now(ZoneInfo("Europe/Athens"))
    employees = _employee_catalog(contexts)
    today_home = build_today_home_context(contexts)
    stores = [
        {"id": int(c["store_id"]), "name": str(c.get("store_name") or "")}
        for c in contexts
    ]
    prompt = {
        "role": (
            "Μετατροπή ελληνικού ή greeklish μηνύματος σε δομημένη draft εντολή εργασίας, "
            "ή απάντηση ερώτησης από την εικόνα εργασίας σήμερα."
        ),
        "rules": [
            "Επίλεξε μόνο store_id και ΑΦΜ που υπάρχουν στους δοσμένους καταλόγους.",
            "Βάλε ΟΛΟΥΣ τους εργαζομένους που ζητά ο χρήστης στα employee_afms και employee_references, με ίδια σειρά.",
            "Για έναν εργαζόμενο πάλι χρησιμοποίησε employee_afms με ένα στοιχείο. Μην συγχωνεύεις πολλαπλά ονόματα.",
            "Επέστρεψε μία εγγραφή στο commands για κάθε διαφορετική ενέργεια/ημερομηνία/ώρα. Επιτρέπονται πολλές διαφορετικές εντολές και πολλοί εργαζόμενοι στο ίδιο μήνυμα.",
            "Αν πολλοί εργαζόμενοι έχουν ακριβώς την ίδια ενέργεια, ημερομηνία και ώρα, μπορούν να βρίσκονται μαζί στην ίδια εγγραφή commands.",
            "Διάβασε greeklish ως ελληνικά (π.χ. ti ora=τι ώρα, klise karta=κλείσε κάρτα, masoura=ΜΑΣΟΥΡΑ) και αντιστοίχισε ονόματα φωνητικά στον κατάλογο.",
            "Αν έστω ένα ζητούμενο όνομα (ελληνικά ή greeklish) δεν αντιστοιχεί μοναδικά στον κατάλογο, επέστρεψε unknown και ζήτησε διευκρίνιση.",
            "Το τώρα σημαίνει την τρέχουσα ώρα Europe/Athens.",
            "Το today_home περιέχει την Αρχική μόνο για ΣΗΜΕΡΑ: ονόματα, ψηφιακό ωράριο, χτυπήματα κάρτας και status.",
            "Αν ο χρήστης ρωτά για την εικόνα εργασίας σήμερα (ποιοι τελειώνουν στις ΧΧ:ΧΧ, τι ώρα τελειώνει ο Χ, ποιος έχει ανοιχτή κάρτα, ποιος είναι σε εργασία) χρησιμοποίησε intent today_info.",
            "Για today_info βάλε την πλήρη απάντηση στα ελληνικά στο clarification_question, μόνο από today_home. employee_afms μπορεί να είναι κενό. Μην ζητάς επιβεβαίωση ενέργειας αν δεν ζητήθηκε ενέργεια.",
            "Για ομαδικές εντολές (π.χ. «κλείσε όσους τελειώνουν στις 15:30») χρησιμοποίησε today_home για να βρεις τους σωστούς ΑΦΜ.",
            "Η ώρα λήξης ωραρίου είναι το schedule_to ή το τελευταίο intervals[].to.",
            "Για «κλείσε τώρα» διάλεξε μόνο εργαζόμενους με status at_work ή needs_checkout που ταιριάζουν στο κριτήριο.",
            "Για έξοδο κάρτας: μόνο ανοιχτές κάρτες (είσοδος χωρίς έξοδο) — όχι ήδη κλεισμένες.",
            "Για είσοδο κάρτας: μόνο όσοι δεν έχουν ήδη δήλωση εισόδου εκείνη την ημέρα.",
            "Για «άνοιξε τώρα» διάλεξε εργαζόμενους με status needs_checkin ή late_arrival που ταιριάζουν στο κριτήριο.",
            "Για εντολές «σήμερα» ή «τώρα» βάλε date=today_home.date.",
            "Μην χρησιμοποιείς today_home για ημερομηνίες εκτός σήμερας.",
            "Για πριν/στις ΧΧ:ΧΧ ή σχετικό χρόνο όπως '10 λεπτά πριν' χρησιμοποίησε retro intent και υπολόγισε ακριβή ώρα HH:MM από το now.",
            "Για άνοιγμα ή κλείσιμο κάρτας 'βάσει ωραρίου/προγράμματος' χρησιμοποίησε αντίστοιχα card_check_in_schedule ή card_check_out_schedule. Μην επινοήσεις ώρα.",
            "Για αλλαγή ωραρίου δώσε hour_from και hour_to.",
            "Για ρεπό χρησιμοποίησε rest_day. Για άδεια χρησιμοποίησε leave.",
            "Το conversation_focus είναι το τρέχον κατάστημα και τα τρέχοντα ονόματα της συνομιλίας. Διατήρησέ τα μέχρι ο χρήστης να ζητήσει ρητά άλλο κατάστημα ή άλλα ονόματα.",
            "Αν το μήνυμα είναι απάντηση (reply) σε ειδοποίηση/εντολή με κατάστημα και όνομα, και τα δύο είναι δεδομένα. Μην τα ξαναρωτήσεις.",
            "Αν το reply_context έχει store_id, employee_afm, employee_afms ή message_text από προηγούμενη εντολή/ειδοποίηση, κληρονόμησέ τα. Μην τα αγνοήσεις επειδή το νέο μήνυμα είναι σύντομο.",
            "«Κλειστόν», «κλείσε», «κλείσε την/την κάρτα» χωρίς άλλο όνομα = κλείσιμο κάρτας των εργαζομένων στο conversation_focus.",
            "Ώρες τύπου 17.00 ή 17,00 είναι 17:00.",
            "Αν κάτι είναι ασαφές επέστρεψε unknown και σύντομη clarification_question στα ελληνικά.",
            "Μην επινοήσεις εργαζόμενο, ΑΦΜ, κατάστημα, ημερομηνία ή ώρα εκτός conversation_focus/reply_context.",
        ],
        "now": now.isoformat(timespec="minutes"),
        "today_home": today_home,
        "message": str(text)[:4096],
        "reply_context": reply_context or {},
        "conversation_focus": _conversation_focus(
            reply_context, contexts=contexts, employees=employees,
        ),
        "allowed_stores": stores,
        "allowed_employees": employees,
    }
    started_at = time.monotonic()
    request_body = {
            "contents": [{"role": "user", "parts": [{"text": json.dumps(prompt, ensure_ascii=False)}]}],
            "generationConfig": {
                "temperature": 0,
                "responseMimeType": "application/json",
                "responseJsonSchema": _SCHEMA,
            },
        }
    models = [Config.GEMINI_MODEL]
    fallback_model = str(Config.GEMINI_FALLBACK_MODEL or "").strip()
    if fallback_model and fallback_model not in models:
        models.append(fallback_model)
    response = None
    last_network_error: requests.RequestException | None = None
    used_model = models[0]
    for model_index, model in enumerate(models):
        attempts = 1 if model_index == 0 and len(models) > 1 else _GEMINI_FALLBACK_ATTEMPTS
        for attempt in range(attempts):
            used_model = model
            try:
                response = requests.post(
                    f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                    headers={"x-goog-api-key": Config.GEMINI_API_KEY, "Content-Type": "application/json"},
                    json=request_body,
                    timeout=(3.05, 10),
                )
            except requests.RequestException as exc:
                last_network_error = exc
                response = None
                if attempt < attempts - 1:
                    time.sleep(0.5)
                continue
            if response.ok or response.status_code not in _GEMINI_RETRY_STATUSES:
                break
            if attempt < attempts - 1:
                time.sleep(0.5)
        if response is not None and (response.ok or response.status_code not in _GEMINI_RETRY_STATUSES):
            break
    duration_ms = max(0, round((time.monotonic() - started_at) * 1000))
    if response is None:
        detail = str(last_network_error or "χωρίς απόκριση")
        raise RuntimeError(f"Gemini network error μετά από model failover: {detail[:300]}")
    if not response.ok:
        raise RuntimeError(f"Gemini HTTP {response.status_code}: {response.text[:500]}")
    response_data = response.json()
    usage_metadata = response_data.get("usageMetadata") or {}
    if not isinstance(usage_metadata, dict):
        usage_metadata = {}
    llm_metadata = {
        "model": str(response_data.get("modelVersion") or used_model)[:128],
        "duration_ms": duration_ms,
        "usage_metadata": usage_metadata,
    }
    return _extract_json(response_data), employees, llm_metadata


def _nested_context(reply_context: dict[str, Any] | None) -> dict[str, Any]:
    raw = dict(reply_context or {})
    nested = raw.get("context")
    if isinstance(nested, dict):
        merged = dict(nested)
        merged.update({key: value for key, value in raw.items() if key != "context" and value not in (None, "", [])})
        return merged
    return raw


def _normalize_clock_time(value: str) -> str:
    text = str(value or "").strip().replace(",", ":").replace(".", ":")
    if re.fullmatch(r"[0-9]:[0-5]\d", text):
        text = f"0{text}"
    return text if re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", text) else str(value or "").strip()


def _clock_from_text(text: str) -> str:
    match = re.search(r"(?:[01]?\d|2[0-3])[.:][0-5]\d", str(text or ""))
    return _normalize_clock_time(match.group(0).replace(".", ":").replace(",", ":")) if match else ""


_GROUP_FOCUS_HINTS = (
    "όσους", "οσους", "όλοι", "ολοι", "όλες", "ολες",
    "τελειώνουν", "ξεκινάνε", "ξεκινανε", "ανοιχτή κάρτα", "ανοιχτη καρτα",
)


def _fold_text(value: str) -> str:
    text = unicodedata.normalize("NFD", str(value or "").casefold())
    return "".join(ch for ch in text if unicodedata.category(ch) != "Mn")


def _mentioned_store_ids(text: str, contexts: list[dict[str, Any]]) -> list[int]:
    folded = _fold_text(text)
    hits: list[int] = []
    for row in contexts:
        name = str(row.get("store_name") or "").strip()
        if name and _fold_text(name) in folded:
            hits.append(int(row["store_id"]))
    return list(dict.fromkeys(hits))


def _mentioned_afms(
    text: str, employees: list[dict[str, Any]], store_id: int | None,
) -> list[str]:
    raw = str(text or "")
    folded = _fold_text(raw)
    hits: list[str] = []
    for emp in employees:
        if store_id is not None and emp.get("store_id") != store_id:
            continue
        afm = str(emp.get("afm") or "").strip()
        name = str(emp.get("name") or "").strip()
        if afm and afm in raw:
            hits.append(afm)
            continue
        if name and len(name) >= 4 and _fold_text(name) in folded:
            hits.append(afm)
            continue
        last = name.split()[0] if name else ""
        if last and len(last) >= 4 and _fold_text(last) in folded:
            hits.append(afm)
    return list(dict.fromkeys(value for value in hits if value))


def _afms_from_text(text: str, employees: list[dict[str, Any]], store_id: int | None) -> list[str]:
    found = [match.group(1) for match in re.finditer(r"ΑΦΜ[:\s]*([0-9]{9})", str(text or ""), flags=re.I)]
    if found:
        return list(dict.fromkeys(found))
    return _mentioned_afms(text, employees, store_id)


def _conversation_focus(
    reply_context: dict[str, Any] | None,
    *,
    contexts: list[dict[str, Any]],
    employees: list[dict[str, Any]],
) -> dict[str, Any]:
    ctx = _nested_context(reply_context)
    allowed = {int(row["store_id"]): row for row in contexts}
    try:
        store_id = int(ctx["store_id"]) if ctx.get("store_id") is not None else None
    except (TypeError, ValueError):
        store_id = None
    message_text = str(ctx.get("message_text") or "")
    if store_id not in allowed:
        named = _mentioned_store_ids(message_text, contexts)
        store_id = named[0] if len(named) == 1 else None
    inherited = ctx.get("employee_afms") if isinstance(ctx.get("employee_afms"), list) else []
    afms = [str(value).strip() for value in inherited if str(value or "").strip()]
    if ctx.get("employee_afm"):
        afms = [str(ctx.get("employee_afm")).strip(), *afms]
    if not afms:
        afms = _afms_from_text(message_text, employees, store_id)
    afms = list(dict.fromkeys(value for value in afms if value))
    names = [
        str(emp.get("name") or "").strip()
        for afm in afms
        for emp in employees
        if emp.get("afm") == afm and (store_id is None or emp.get("store_id") == store_id)
    ]
    store_name = str((allowed.get(store_id) or {}).get("store_name") or "").strip() if store_id else ""
    return {
        "locked": bool(ctx.get("focus_locked")),
        "store_id": store_id,
        "store_name": store_name or None,
        "employee_afms": afms,
        "employee_names": [name for name in names if name],
        "source": "reply" if ctx.get("focus_locked") else "previous",
    }


def _inherit_conversation_context(
    parsed: dict[str, Any],
    *,
    contexts: list[dict[str, Any]],
    employees: list[dict[str, Any]],
    reply_context: dict[str, Any] | None,
    user_text: str,
) -> None:
    focus = _conversation_focus(reply_context, contexts=contexts, employees=employees)
    allowed_store_ids = {int(row["store_id"]) for row in contexts}
    mentioned_stores = _mentioned_store_ids(user_text, contexts)
    store_id = parsed.get("store_id")
    try:
        store_id = int(store_id) if store_id is not None else None
    except (TypeError, ValueError):
        store_id = None
    if mentioned_stores:
        if len(mentioned_stores) == 1:
            store_id = mentioned_stores[0]
    elif focus.get("store_id") in allowed_store_ids:
        store_id = int(focus["store_id"])
    if store_id in allowed_store_ids:
        parsed["store_id"] = store_id

    raw_afms = parsed.get("employee_afms")
    if not isinstance(raw_afms, list):
        raw_afms = [parsed.get("employee_afm")] if parsed.get("employee_afm") else []
    parsed_afms = [str(value).strip() for value in raw_afms if str(value or "").strip()]
    mentioned_afms = _mentioned_afms(user_text, employees, store_id if store_id in allowed_store_ids else None)
    group_query = any(hint in str(user_text or "").casefold() for hint in _GROUP_FOCUS_HINTS)
    if mentioned_afms:
        afms = mentioned_afms
    elif not group_query and focus.get("employee_afms"):
        afms = [str(value).strip() for value in focus["employee_afms"] if str(value or "").strip()]
    else:
        afms = parsed_afms
    if afms:
        parsed["employee_afms"] = list(dict.fromkeys(afms))
        parsed["employee_afm"] = parsed["employee_afms"][0] if len(parsed["employee_afms"]) == 1 else None

    time_value = _normalize_clock_time(str(parsed.get("time") or ""))
    if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", time_value):
        time_value = _clock_from_text(user_text)
    if re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", time_value):
        parsed["time"] = time_value

    intent = str(parsed.get("intent") or "unknown")
    folded = str(user_text or "").casefold()
    if intent == "unknown" and (parsed.get("employee_afms") or parsed.get("employee_afm")):
        if any(token in folded for token in ("κλειστ", "κλείσε", "close", "checkout", "έξοδ")):
            parsed["intent"] = "card_check_out_retro" if parsed.get("time") else "card_check_out_now"
        elif any(token in folded for token in ("άνοιξε", "ανοιξε", "open", "checkin", "είσοδ", "εισοδ")):
            parsed["intent"] = "card_check_in_retro" if parsed.get("time") else "card_check_in_now"
    if str(parsed.get("intent") or "unknown") not in {"unknown", "today_info"} and not str(parsed.get("date") or "").strip():
        parsed["date"] = datetime.now(ZoneInfo("Europe/Athens")).date().isoformat()


def _validate_single_command(
    parsed: dict[str, Any], *, contexts: list[dict[str, Any]], employees: list[dict[str, Any]],
    reply_context: dict[str, Any] | None = None, user_text: str = "",
) -> tuple[str, dict[str, Any], str]:
    _inherit_conversation_context(
        parsed, contexts=contexts, employees=employees,
        reply_context=reply_context, user_text=user_text,
    )
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

    raw_afms = parsed.get("employee_afms")
    if not isinstance(raw_afms, list):
        raw_afms = [parsed.get("employee_afm")] if parsed.get("employee_afm") else []
    afms: list[str] = []
    for value in raw_afms:
        afm = str(value or "").strip()
        if afm and afm not in afms:
            afms.append(afm)
    parsed["employee_afms"] = afms
    # Keep the legacy scalar only for single-person tasks and DB/query compatibility.
    parsed["employee_afm"] = afms[0] if len(afms) == 1 else None

    matches = [
        employee for afm in afms
        for employee in employees
        if employee["store_id"] == store_id and employee["afm"] == afm
    ]
    if intent not in {"unknown", *_INFO_INTENTS} and (not afms or len(matches) != len(afms)):
        errors.append("Δεν προσδιορίστηκαν μοναδικά όλοι οι εργαζόμενοι του καταστήματος")

    date = str(parsed.get("date") or "").strip()
    if intent not in {"unknown", *_INFO_INTENTS} and not _is_iso_date(date):
        errors.append("Δεν προσδιορίστηκε έγκυρη ημερομηνία")
    today_iso = datetime.now(ZoneInfo("Europe/Athens")).date().isoformat()
    if intent.startswith("card_check_") and _is_iso_date(date) and date > today_iso:
        errors.append(future_card_punch_blocked_message())
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
    if intent == "today_info" and not str(parsed.get("clarification_question") or "").strip():
        errors.append("Δεν δόθηκε απάντηση από την εικόνα εργασίας σήμερα")
    if intent == "unknown":
        errors.append(str(parsed.get("clarification_question") or "Δεν αναγνωρίστηκε υποστηριζόμενη εντολή"))

    schedule_times: dict[str, str] = {}
    if intent in {"card_check_in_schedule", "card_check_out_schedule"} and store_id in allowed_store_ids and _is_iso_date(date):
        from app.date_util import format_date_for_ergani
        from app.repo_schedule import list_schedule_for_store

        store_context = next(c for c in contexts if int(c["store_id"]) == store_id)
        schedule_rows = list_schedule_for_store(
            str(store_context.get("employer_afm") or ""),
            str(store_context.get("branch_aa") or "0"),
            format_date_for_ergani(date),
        )
        field = "hour_from" if intent == "card_check_in_schedule" else "hour_to"
        for match in matches:
            afm = str(match.get("afm") or "")
            values = [
                str(row.get(field) or "").strip()[:5]
                for row in schedule_rows if str(row.get("employee_afm") or "").strip() == afm
            ]
            values = [value for value in values if re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", value)]
            if values:
                schedule_times[afm] = min(values) if field == "hour_from" else max(values)
            else:
                errors.append(f"Δεν βρέθηκε ώρα {'έναρξης' if field == 'hour_from' else 'λήξης'} στο ωράριο για {match.get('name') or afm}")
        parsed["resolved_schedule_times"] = schedule_times

    skipped_card: list[str] = []
    if (
        intent.startswith("card_check_")
        and store_id in allowed_store_ids
        and _is_iso_date(date)
        and matches
        and not errors
    ):
        from app.work_card_guards import new_card_punch_blocked_reason

        store_context = next(c for c in contexts if int(c["store_id"]) == store_id)
        employer_afm = str(store_context.get("employer_afm") or "")
        branch_aa = str(store_context.get("branch_aa") or "0")
        eligible_matches: list[dict[str, Any]] = []
        for match in matches:
            afm = str(match.get("afm") or "")
            event_at = None
            if intent.endswith("_retro"):
                event_at = f"{date}T{time_value}:00"
            elif intent.endswith("_schedule"):
                sched_time = schedule_times.get(afm)
                if sched_time:
                    event_at = f"{date}T{sched_time}:00"
            reason = new_card_punch_blocked_reason(
                intent=intent,
                employer_afm=employer_afm,
                branch_aa=branch_aa,
                employee_afm=afm,
                reference_date_iso=date,
                event_at=event_at,
            )
            if reason:
                skipped_card.append(f"{match.get('name') or afm}: {reason}")
            else:
                eligible_matches.append(match)
        if eligible_matches:
            matches = eligible_matches
            afms = [str(item.get("afm") or "") for item in matches if str(item.get("afm") or "")]
            parsed["employee_afms"] = afms
            parsed["employee_afm"] = afms[0] if len(afms) == 1 else None
            if skipped_card:
                parsed["skipped_card_employees"] = skipped_card
        else:
            errors.extend(
                skipped_card
                or ["Κανένας εργαζόμενος δεν είναι επιλέξιμος για αυτή την ενέργεια κάρτας"]
            )

    validation = {"valid": not errors, "errors": errors, "execution_enabled": False}
    if errors:
        status = "needs_clarification"
    elif intent in _INFO_INTENTS:
        status = "answered"
    else:
        status = "draft"
    if matches:
        names = ", ".join(str(match.get("name") or match.get("afm") or "εργαζόμενος") for match in matches)
    else:
        references = parsed.get("employee_references")
        if not isinstance(references, list):
            references = [parsed.get("employee_reference")] if parsed.get("employee_reference") else []
        names = ", ".join(str(value).strip() for value in references if str(value).strip()) or "εργαζόμενος"
    try:
        display_date = datetime.strptime(date, "%Y-%m-%d").strftime("%d/%m/%Y")
    except ValueError:
        display_date = date or "—"
    labels = {
        "card_check_in_now": "Άνοιγμα κάρτας τώρα",
        "card_check_out_now": "Κλείσιμο κάρτας τώρα",
        "card_check_in_retro": f"Άνοιγμα κάρτας στις {time_value}",
        "card_check_out_retro": f"Κλείσιμο κάρτας στις {time_value}",
        "card_check_in_schedule": "Άνοιγμα κάρτας",
        "card_check_out_schedule": "Κλείσιμο κάρτας",
        "schedule_change": f"Αλλαγή ωραρίου σε {parsed.get('hour_from') or '—'}–{parsed.get('hour_to') or '—'}",
        "rest_day": "Δήλωση ρεπό",
        "leave": f"Δήλωση άδειας ({parsed.get('leave_type') or 'τύπος προς διευκρίνιση'})",
        "today_info": "Πληροφορία σήμερα",
        "unknown": "Μη αναγνωρισμένη εντολή",
    }
    if intent == "today_info":
        proposed = str(parsed.get("clarification_question") or "").strip()
    elif intent in {"card_check_in_schedule", "card_check_out_schedule"} and matches:
        proposed = "\n".join(
            f"{match.get('name') or match.get('afm')} · {display_date} · {labels[intent]} {schedule_times.get(str(match.get('afm') or ''), '—')}"
            for match in matches
        )
    else:
        proposed = f"{names} · {display_date} · {labels[intent]}"
    if skipped_card:
        proposed += "\n(Παραλείφθηκαν: " + "; ".join(skipped_card) + ")"
    return status, validation, proposed


def validate_and_describe(
    parsed: dict[str, Any], *, contexts: list[dict[str, Any]], employees: list[dict[str, Any]],
    reply_context: dict[str, Any] | None = None, user_text: str = "",
) -> tuple[str, dict[str, Any], str]:
    commands = parsed.get("commands")
    if not isinstance(commands, list):
        return _validate_single_command(
            parsed, contexts=contexts, employees=employees,
            reply_context=reply_context, user_text=user_text,
        )

    normalized = [command for command in commands if isinstance(command, dict)]
    if not normalized:
        validation = {"valid": False, "errors": ["Δεν αναγνωρίστηκε καμία εντολή"], "execution_enabled": False}
        return "needs_clarification", validation, "Μη αναγνωρισμένη εντολή"

    proposed_lines: list[str] = []
    errors: list[str] = []
    store_ids: set[int] = set()
    statuses: list[str] = []
    for index, command in enumerate(normalized, start=1):
        status, validation, proposed = _validate_single_command(
            command, contexts=contexts, employees=employees,
            reply_context=reply_context, user_text=user_text,
        )
        proposed_lines.extend(line for line in proposed.splitlines() if line.strip())
        statuses.append(status)
        if status == "needs_clarification":
            errors.extend(f"Εντολή {index}: {error}" for error in validation.get("errors") or [])
        if command.get("store_id") is not None:
            store_ids.add(int(command["store_id"]))

    parsed["commands"] = normalized
    if len(store_ids) == 1:
        parsed["store_id"] = next(iter(store_ids))
    if errors:
        validation = {"valid": False, "errors": errors, "execution_enabled": False}
        return "needs_clarification", validation, "\n".join(proposed_lines)
    if statuses and all(item == "answered" for item in statuses):
        validation = {"valid": True, "errors": [], "execution_enabled": False}
        return "answered", validation, "\n".join(proposed_lines)
    validation = {"valid": True, "errors": [], "execution_enabled": True}
    return "draft", validation, "\n".join(proposed_lines)
