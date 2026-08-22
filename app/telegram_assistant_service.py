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
    "cancel_pending",
    "unknown",
}
_INFO_INTENTS = {"today_info", "cancel_pending"}

_GEMINI_RETRY_STATUSES = {429, 500, 502, 503, 504}
# Hard wall-clock budget for all Gemini attempts so the chat stays ≤ ~10s.
_GEMINI_TOTAL_BUDGET_SEC = 8.0
_GEMINI_CONNECT_TIMEOUT = 2.0


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
        "pending_intent": {"type": ["string", "null"], "enum": [
            None,
            *sorted(ALLOWED_INTENTS - {"unknown", "today_info", "cancel_pending"}),
        ]},
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
        "ambiguous_employee_afms": {"type": "array", "items": {"type": "string"}},
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
    return _normalize_parsed_command(parsed)


def _normalize_parsed_command(parsed: Any) -> dict[str, Any]:
    if not isinstance(parsed, dict):
        raise ValueError("Ο parser δεν επέστρεψε JSON object")
    commands = parsed.get("commands")
    if isinstance(commands, list):
        valid_commands = [command for command in commands if isinstance(command, dict)]
        if len(valid_commands) == 1:
            return valid_commands[0]
        parsed["commands"] = valid_commands
    return parsed


def _call_gemini(prompt: dict[str, Any], *, deadline: float) -> tuple[dict[str, Any], dict[str, Any]]:
    """Gemini με failover μοντέλων + σύντομα retries σε 503/429."""
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
    last_http_error = ""
    used_model = models[0]
    started_at = time.monotonic()

    for model in models:
        for _attempt in range(2):
            remaining = deadline - time.monotonic()
            if remaining < (_GEMINI_CONNECT_TIMEOUT + 2.0):
                break
            read_timeout = min(6.0, max(2.0, remaining - 0.25))
            used_model = model
            try:
                response = requests.post(
                    f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
                    headers={
                        "x-goog-api-key": Config.GEMINI_API_KEY,
                        "Content-Type": "application/json",
                    },
                    json=request_body,
                    timeout=(_GEMINI_CONNECT_TIMEOUT, read_timeout),
                )
            except requests.RequestException as exc:
                last_network_error = exc
                response = None
                time.sleep(min(0.6, max(0.2, remaining / 10)))
                continue
            if response.ok:
                break
            last_http_error = f"HTTP {response.status_code}: {response.text[:300]}"
            if response.status_code not in _GEMINI_RETRY_STATUSES:
                break
            time.sleep(min(0.8, max(0.25, remaining / 8)))
        if response is not None and response.ok:
            break

    duration_ms = max(0, round((time.monotonic() - started_at) * 1000))
    if response is None:
        detail = str(last_network_error or last_http_error or "χωρίς απόκριση")
        raise RuntimeError(f"Gemini network error μετά από failover: {detail[:300]}")
    if not response.ok:
        raise RuntimeError(f"Gemini {last_http_error or response.status_code}")
    response_data = response.json()
    usage_metadata = response_data.get("usageMetadata") or {}
    if not isinstance(usage_metadata, dict):
        usage_metadata = {}
    llm_metadata = {
        "model": str(response_data.get("modelVersion") or used_model)[:128],
        "duration_ms": duration_ms,
        "provider": "gemini",
        "usage_metadata": usage_metadata,
    }
    return _extract_json(response_data), llm_metadata


def _assistant_prompt_guide() -> list[str]:
    """Compact, non-duplicated guidance (token-cheap). Examples are non-binding."""
    return [
        "Parser εντολών erganiOS (όχι chatbot). Ελληνικά/greeklish → JSON. Μην γράφεις meta («το διορθώνω»).",
        "Μόνο store_id/ΑΦΜ από allowed_*. Ονόματα φωνητικά (dionisi→ΔΙΟΝΥΣΙΟΣ, fotopoulou→ΦΩΤΟΠΟΥΛΟΣ). Greeklish=ελληνικά.",
        "Πολλά ονόματα/επώνυμα στο μήνυμα («του Χ και του Υ»): αν καθένα ταιριάζει σε διαφορετικό εργαζόμενο, βάλε ΟΛΑ τα ΑΦΜ σε employee_afms. ΜΗΝ ρωτάς «Εννοείτε…» ανάμεσα σε άσχετα επώνυμα.",
        "Ίδιο/παρόμοιο επώνυμο χωρίς διακριτό όνομα (Φωτόπουλος×2, VLASENKO×2): κράτησε στο intent την ενέργεια που ήδη ζήτησε ο χρήστης, βάλε την και στο pending_intent, γράψε «Εννοείτε του Χ ή του Υ;» (όλες οι επιλογές, άρθρο φύλου), ambiguous_employee_afms=όλα τα υποψήφια και employee_afms=[]. Μην αλλάζεις την ενέργεια σε unknown μόνο επειδή λείπει η επιλογή προσώπου.",
        "pending_clarification.name_choice: το message είναι η απάντηση ως έχει· επίλεξε ένα ΑΦΜ από candidate_* και κληρονόμησε preserve_*. Αν preserve_intent λείπει/είναι unknown (παλιό task), ανάκτησε την ενέργεια από original_message και κράτησέ την στο intent.",
        "Όσο υπάρχει pending_clarification, το message αφορά ΠΑΝΤΑ την ίδια τρέχουσα εντολή. Συμπλήρωσε ή διόρθωσε μόνο όσα ζητά ο χρήστης και κληρονόμησε όλα τα υπόλοιπα preserve_*· νέα ανεξάρτητη εντολή δεν δημιουργείται μέχρι εκτέλεση/ακύρωση/τερματισμό.",
        "Ακύρωση/απόρριψη οποιασδήποτε διατύπωσης (ακύρωσε, άστο, γάμα το, μην το κάνεις, #N…) → cancel_pending. Όχι whitelist.",
        "Κάρτα — ΚΡΙΣΙΜΟ: μην αντιστρέφεις ποτέ είσοδο/έξοδο. Ρητή λεξηλογία: άνοιξε/open/clock in/check in/checkin/είσοδος → card_check_in_*· κλείσε/close/clock out/check out/checkout/έξοδος → card_check_out_*. «Άνοιξε κάρτα» ΠΟΤΕ check_out. «Κλείσε κάρτα» ΠΟΤΕ check_in. Αν το μήνυμα έχει ρήμα άνοιγματος, το intent ΠΡΕΠΕΙ να περιέχει check_in.",
        "Κάρτα χωρίς ώρα («άνοιξε/κλείσε κάρτα») = *_now, time=null. «πριν Χ λεπτά» / «Χ λεπτά πριν» = *_retro από το now (τώρα − Χ)· ΠΟΤΕ όχι από την ώρα εισόδου/εξόδου της κάρτας. Αν εννοεί offset από χτύπημα, πρέπει να το πει ρητά («Χ λεπτά πριν την είσοδο/έξοδο»). «στις 10» = *_retro ακριβώς. Μην μαντεύεις ώρα.",
        "Αλλαγή ωραρίου / νέο ωράριο / από–έως (π.χ. «15:00 έως 21:40», «αλλαγή ωραρίου») → intent=schedule_change με hour_from+hour_to. ΜΗΝ βάζεις unknown όταν υπάρχουν ώρες από–έως.",
        "Πολλές εντολές/εργαζόμενοι OK. Ίδια ενέργεια+ημερομηνία+ώρα → μία εγγραφή commands με πολλά employee_afms.",
        "today_home είναι ΠΑΝΤΑ παρόν: stores=σήμερα (πλήρες)· yesterday=μόνο ανοιχτές κάρτες χθες (overnight). Ερωτήσεις σήμερα → stores. Ερωτήσεις/κλείσιμο ανοιχτών «χθες»/εχθές → yesterday + date=yesterday_date. today_info: βάλε την πλήρη απάντηση στο clarification_question από τα πραγματικά δεδομένα. Μην λες «δεν υπάρχουν δεδομένα» αν υπάρχει yesterday· αν open_count=0 πες ρητά ότι δεν υπάρχουν ανοιχτές εκείνη την ημέρα.",
        "Ομαδικό/κριτήριο (όσους, όσοι δουλεύουν, μετά τις Χ, τελειώνουν…): ΜΗΝ χρησιμοποιείς ονόματα από conversation_focus· διάλεξε ΑΦΜ από today_home.stores (σήμερα) ή today_home.yesterday (χθες ανοιχτές) βάσει κριτηρίου.",
        "Έξοδος: μόνο ανοιχτές κάρτες· ήδη κλειστές παραλείπονται. Είσοδος: χωρίς ήδη είσοδο· ήδη ανοιχτές παραλείπονται. *_now: at_work/needs_checkout ή needs_checkin/late_arrival. Κλείσιμο ανοιχτών χθες → card_check_out_retro ή *_now με date=yesterday_date και ΑΦΜ ΜΟΝΟ από yesterday (όχι επιπλέον ονόματα). «κλείσε όλες/όσους» = όλα τα ΑΦΜ ανοιχτών της ημερομηνίας.",
        "Βάσει ωραρίου → *_schedule χωρίς ώρα. Ρεπό=rest_day. Άδεια=leave+leave_type. Ωράριο=hour_from/hour_to.",
        "conversation_focus/reply_context κληρονομούνται μόνο σε σύντομες απαντήσεις για τα ΙΔΙΑ πρόσωπα. Ώρες 17.00→17:00. Ασαφές→unknown+clarification_question.",
    ]


def parse_command(
    *, text: str, contexts: list[dict[str, Any]], reply_context: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    if not Config.GEMINI_API_KEY and not (Config.OPENAI_API_KEY or "").strip():
        raise RuntimeError("Δεν έχει ρυθμιστεί GEMINI_API_KEY ούτε OPENAI_API_KEY")
    now = datetime.now(ZoneInfo("Europe/Athens"))
    employees = _employee_catalog(contexts)
    stores = [
        {"id": int(c["store_id"]), "name": str(c.get("store_name") or "")}
        for c in contexts
    ]

    # If we can resolve a single store from focus/reply/text, narrow employees & today_home
    focus = _conversation_focus(reply_context, contexts=contexts, employees=employees)
    group_query = _is_group_or_criteria_query(text)
    if group_query:
        # Do not leak previous person names into Gemini for criteria queries.
        focus = {
            **focus,
            "employee_afms": [],
            "employee_names": [],
            "note": (
                "Ομαδικό/κριτήριο μήνυμα: αγνόησε προηγούμενα ονόματα· "
                "διάλεξε ΑΦΜ μόνο από today_home / allowed_employees βάσει κριτηρίου."
            ),
        }
    # Explicit store in the message beats sticky conversation focus (other stores).
    focused_store_id: int | None = None
    mentioned = _mentioned_store_ids(text, contexts)
    if len(mentioned) == 1:
        focused_store_id = mentioned[0]
    elif focus.get("store_id") and int(focus["store_id"]) in {int(c["store_id"]) for c in contexts}:
        focused_store_id = int(focus["store_id"])
    if focused_store_id:
        employees = [e for e in employees if e["store_id"] == focused_store_id]

    # Always attach today's home snapshot — most commands/questions are about today.
    today_home = build_today_home_context(contexts)
    if focused_store_id:
        today_stores = today_home.get("stores") or []
        today_home = {
            **today_home,
            "stores": [s for s in today_stores if int(s.get("store_id") or 0) == focused_store_id],
        }

    prompt: dict[str, Any] = {
        "role": "erganiOS command parser → structured JSON draft or today_info answer.",
        "guide": _assistant_prompt_guide(),
        "now": now.isoformat(timespec="minutes"),
        "message": str(text)[:4096],
        "reply_context": reply_context or {},
        "conversation_focus": focus,
        "allowed_stores": stores,
        "allowed_employees": employees,
        "today_home": today_home,
    }

    errors: list[str] = []

    def _try_gemini() -> tuple[dict[str, Any], dict[str, Any]] | None:
        if not Config.GEMINI_API_KEY:
            errors.append("gemini: no API key")
            return None
        try:
            deadline = time.monotonic() + _GEMINI_TOTAL_BUDGET_SEC
            return _call_gemini(prompt, deadline=deadline)
        except Exception as ex:
            errors.append(f"gemini: {ex}")
            return None

    def _try_openai() -> tuple[dict[str, Any], dict[str, Any]] | None:
        try:
            from app.openai_assistant_client import generate_json, openai_enabled

            if not openai_enabled():
                errors.append("openai: disabled")
                return None
            raw, llm_metadata = generate_json(
                prompt_obj=prompt,
                timeout_sec=float(Config.OPENAI_TIMEOUT_SEC or 20),
            )
            return _normalize_parsed_command(raw), llm_metadata
        except Exception as ex:
            errors.append(f"openai: {ex}")
            return None

    providers = {
        "gemini": _try_gemini,
        "openai": _try_openai,
    }
    order_raw = str(Config.ASSISTANT_LLM_ORDER or "gemini,openai")
    order: list[str] = []
    for token in order_raw.replace(";", ",").split(","):
        name = token.strip().casefold()
        if name in {"gemini", "google"}:
            name = "gemini"
        elif name in {"openai", "gpt"}:
            name = "openai"
        else:
            continue
        if name not in order:
            order.append(name)
    if not order:
        order = ["gemini", "openai"]

    for name in order:
        runner = providers.get(name)
        if not runner:
            continue
        result = runner()
        if result is not None:
            parsed, llm_metadata = result
            llm_metadata = dict(llm_metadata or {})
            llm_metadata["llm_order"] = order
            llm_metadata["llm_used"] = name
            return parsed, employees, llm_metadata

    # Rule-based today_info — τελευταία γραμμή άμυνας χωρίς LLM
    if Config.ASSISTANT_RULE_FALLBACK_ENABLED:
        try:
            from app.assistant_rule_fallback import rule_based_parse

            store_name = ""
            if focused_store_id is not None:
                store_name = next(
                    (str(s["name"]) for s in stores if int(s["id"]) == int(focused_store_id)),
                    "",
                )
            ruled = rule_based_parse(
                text=text,
                store_id=focused_store_id,
                store_name=store_name,
                today_home=today_home,
            )
            if ruled:
                return ruled, employees, {
                    "model": "rule_fallback",
                    "duration_ms": 0,
                    "provider": "rules",
                    "llm_order": order,
                    "llm_used": "rules",
                    "usage_metadata": {},
                    "errors": errors,
                }
        except Exception as ex:
            errors.append(f"rules: {ex}")

    detail = " | ".join(errors)[:400] if errors else "χωρίς λεπτομέρειες"
    raise RuntimeError(
        "Προσωρινή αδυναμία ανάλυσης εντολής (Gemini/OpenAI). "
        f"Δοκιμάστε ξανά σε λίγο. [{detail}]"
    )


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
    "οσους", "οσοι", "οσες", "ολους", "ολες", "ολοι", "ολα",
    "τελειων", "ξεκινα", "δουλευ", "εργαζ", "ανοιχτ",
    "μετα τι", "μετα τις", "πριν τι", "πριν τις",
)


def _fold_text(value: str) -> str:
    text = unicodedata.normalize("NFD", str(value or "").casefold())
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    # Greek casefold maps capital Σ to final ς; normalize to σ for matching.
    return text.replace("ς", "σ")


_GREEK_TO_LATIN = str.maketrans({
    "α": "a", "β": "v", "γ": "g", "δ": "d", "ε": "e", "ζ": "z", "η": "i",
    "θ": "th", "ι": "i", "κ": "k", "λ": "l", "μ": "m", "ν": "n", "ξ": "x",
    "ο": "o", "π": "p", "ρ": "r", "σ": "s", "τ": "t", "υ": "i", "φ": "f",
    "χ": "ch", "ψ": "ps", "ω": "o",
})


def _greeklish_fold(value: str) -> str:
    """Fold + approximate Greek→Latin so «Ερατο» matches store name ERATO."""
    return _fold_text(value).translate(_GREEK_TO_LATIN)


def _is_group_or_criteria_query(text: str) -> bool:
    folded = f" {_fold_text(text)} "
    return any(hint in folded for hint in _GROUP_FOCUS_HINTS)


def _edit_distance(left: str, right: str) -> int:
    if left == right:
        return 0
    if not left:
        return len(right)
    if not right:
        return len(left)
    previous = list(range(len(right) + 1))
    for i, a in enumerate(left, start=1):
        current = [i]
        for j, b in enumerate(right, start=1):
            insert = current[j - 1] + 1
            delete = previous[j] + 1
            replace = previous[j - 1] + (a != b)
            current.append(min(insert, delete, replace))
        previous = current
    return previous[-1]


def _surname_stem(value: str) -> str:
    text = _fold_text(value)
    if not text:
        return ""
    endings = (
        "πουλου", "πουλος", "οπουλος", "οπουλου", "ιδης", "ιδου", "αδης", "αδου",
        "ος", "ου", "ας", "ης", "ων", "ις",
    )
    for ending in endings:
        folded_ending = _fold_text(ending)
        if len(text) > len(folded_ending) + 2 and text.endswith(folded_ending):
            return text[: -len(folded_ending)]
    if len(text) > 3 and text[-1] in "αηω":
        return text[:-1]
    return text


def _name_parts(employee: dict[str, Any]) -> tuple[str, str]:
    name = str(employee.get("name") or "").strip()
    parts = [part for part in name.split() if part]
    if not parts:
        return "", ""
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], " ".join(parts[1:])


def _genitive_first_name(first_name: str) -> str:
    raw = str(first_name or "").strip()
    if not raw:
        return ""
    folded = _fold_text(raw)
    if folded.endswith(_fold_text("ος")) and len(folded) > 2:
        return (folded[:-2] + "ου").upper()
    if folded.endswith(_fold_text("ας")) and len(folded) > 2:
        return (folded[:-2] + "α").upper()
    if folded.endswith(_fold_text("ης")) and len(folded) > 2:
        return (folded[:-2] + "η").upper()
    if folded.endswith("η") and len(folded) > 1:
        return (folded + "σ").upper()
    if folded.endswith("α") and len(folded) > 1 and not folded.endswith("ια"):
        return (folded + "σ").upper()
    if folded.endswith("ια") and len(folded) > 2:
        return (folded[:-1] + "ασ").upper()
    return raw.upper()


def _stems_similar(left: str, right: str) -> bool:
    if not left or not right:
        return False
    if left == right:
        return True
    if left.startswith(right) or right.startswith(left):
        shorter, longer = (left, right) if len(left) <= len(right) else (right, left)
        if len(shorter) >= 4 and len(longer) - len(shorter) <= 2:
            return True
    return _edit_distance(left, right) <= 1 and min(len(left), len(right)) >= 4


def _employee_surname_matches_token(surname: str, token: str) -> bool:
    last = _fold_text(surname)
    needle = _fold_text(token)
    if not last or not needle or len(needle) < 4:
        return False
    if needle in last or last in needle:
        return True
    return _stems_similar(_surname_stem(last), _surname_stem(needle))


def _query_tokens(text: str) -> list[str]:
    folded = _fold_text(text)
    stop = {
        "ανοιξε", "κλεισε", "κλειστον", "καρτα", "την", "τον", "του", "της", "τους", "τις",
        "τωρα", "σημερα", "παρακαλω", "για", "και", "στο", "στη", "στην", "απο", "με",
        "ρεπο", "αδεια", "ωραριο", "open", "close", "card", "now", "today",
    }
    tokens = re.findall(r"[a-zα-ω]{4,}", folded)
    return [token for token in tokens if token not in stop]


def _first_name_stem(value: str) -> str:
    text = _fold_text(value)
    if not text:
        return ""
    for ending in ("ου", "ος", "ας", "ης", "ων", "ις", "α", "η"):
        folded_ending = _fold_text(ending)
        if len(text) > len(folded_ending) + 2 and text.endswith(folded_ending):
            return text[: -len(folded_ending)]
    return text


def _first_name_in_text(text: str, first_name: str) -> bool:
    first = _fold_text(first_name)
    if not first or len(first) < 3:
        return False
    folded = _fold_text(text)
    if first in folded:
        return True
    genitive = _fold_text(_genitive_first_name(first_name))
    if genitive and len(genitive) >= 3 and genitive in folded:
        return True
    stem = _first_name_stem(first_name)
    if len(stem) < 4:
        return False
    for token in re.findall(r"[a-zα-ω]{3,}", folded):
        token_stem = _first_name_stem(token)
        if token_stem == stem or stem.startswith(token_stem) or token_stem.startswith(stem):
            if min(len(stem), len(token_stem)) >= 4:
                return True
        if stem in token or token in stem:
            return True
    return False


def _mentioned_store_ids(text: str, contexts: list[dict[str, Any]]) -> list[int]:
    folded = _fold_text(text)
    greeklish = _greeklish_fold(text)
    hits: list[int] = []
    for row in contexts:
        name = str(row.get("store_name") or "").strip()
        if not name:
            continue
        name_fold = _fold_text(name)
        name_gl = _greeklish_fold(name)
        if (name_fold and name_fold in folded) or (name_gl and name_gl in greeklish):
            hits.append(int(row["store_id"]))
            continue
        # Short latin store codes (ERATO) vs Greek speech (Ερατο / Ερατοσθένους).
        if name_gl and len(name_gl) >= 4 and name_gl in greeklish:
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
        surname, first = _name_parts(emp)
        if afm and afm in raw:
            hits.append(afm)
            continue
        if name and len(name) >= 4 and _fold_text(name) in folded:
            hits.append(afm)
            continue
        if first and _first_name_in_text(raw, first):
            hits.append(afm)
            continue
        for token in _query_tokens(raw):
            if _employee_surname_matches_token(surname, token):
                hits.append(afm)
                break
            if first and (
                _fold_text(first) == _fold_text(token)
                or _first_name_stem(first) == _first_name_stem(token)
                or _first_name_in_text(token, first)
            ):
                hits.append(afm)
                break
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
    store_name = str((allowed.get(store_id) or {}).get("store_name") or "").strip() if store_id else ""
    # After cancel, keep store only — do not inherit previous people.
    if ctx.get("reset_conversation_focus") or str(ctx.get("notification_type") or "") == "assistant_cancelled":
        return {
            "locked": False,
            "store_id": store_id,
            "store_name": store_name or None,
            "employee_afms": [],
            "employee_names": [],
            "source": "reset",
        }
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
    pending_clarification = {}
    if isinstance(reply_context, dict):
        pending_clarification = reply_context.get("pending_clarification") or {}
        if not isinstance(pending_clarification, dict):
            pending_clarification = {}
    group_query = _is_group_or_criteria_query(user_text)
    named_in_message = _mentioned_afms(
        user_text, employees, store_id if store_id in allowed_store_ids else None,
    )
    # Name-choice / group: trust Gemini. Sticky focus: if the user did not name
    # anyone this turn, keep the previous people even if the model invents AFMs.
    if pending_clarification.get("kind") == "name_choice" and parsed_afms:
        afms = parsed_afms
    elif group_query:
        afms = parsed_afms
    elif not named_in_message and focus.get("employee_afms"):
        afms = [str(value).strip() for value in focus["employee_afms"] if str(value or "").strip()]
    elif parsed_afms:
        afms = parsed_afms
    elif focus.get("employee_afms"):
        afms = [str(value).strip() for value in focus["employee_afms"] if str(value or "").strip()]
    else:
        afms = []
    if afms:
        parsed["employee_afms"] = list(dict.fromkeys(afms))
        parsed["employee_afm"] = parsed["employee_afms"][0] if len(parsed["employee_afms"]) == 1 else None
    elif group_query:
        parsed["employee_afms"] = []
        parsed["employee_afm"] = None

    time_value = _normalize_clock_time(str(parsed.get("time") or ""))
    if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", time_value):
        time_value = _clock_from_text(user_text)
    if re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", time_value):
        parsed["time"] = time_value

    intent = str(parsed.get("intent") or "unknown")
    # Common LLM aliases → canonical intents
    intent_aliases = {
        "change_schedule": "schedule_change",
        "schedule_update": "schedule_change",
        "update_schedule": "schedule_change",
        "modify_schedule": "schedule_change",
        "wto_daily": "schedule_change",
        "wtodaily": "schedule_change",
        "ωραριο": "schedule_change",
        "αλλαγη_ωραριου": "schedule_change",
        "αλλαγηωραριου": "schedule_change",
    }
    alias_key = _fold_text(intent).replace(" ", "_").replace("-", "_")
    if alias_key in intent_aliases:
        intent = intent_aliases[alias_key]
        parsed["intent"] = intent

    for field in ("hour_from", "hour_to"):
        hv = _normalize_clock_time(str(parsed.get(field) or ""))
        if re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", hv):
            parsed[field] = hv
        elif parsed.get(field) not in (None, ""):
            # try extract from user text for that field later if needed
            pass

    folded = _fold_text(user_text)
    has_employee = bool(parsed.get("employee_afms") or parsed.get("employee_afm"))
    hf = str(parsed.get("hour_from") or "")
    ht = str(parsed.get("hour_to") or "")
    has_schedule_hours = bool(
        re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", hf)
        and re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", ht)
    )
    if intent == "unknown" and has_employee and has_schedule_hours:
        # Από–έως με πρόσωπο = αλλαγή ωραρίου (όχι κάρτα· η κάρτα χρησιμοποιεί time).
        parsed["intent"] = "schedule_change"
        intent = "schedule_change"
    elif intent == "unknown" and has_employee:
        from app.assistant_card_intent import card_action_direction_from_text

        direction = card_action_direction_from_text(user_text)
        if direction == "check_out":
            parsed["intent"] = "card_check_out_retro" if parsed.get("time") else "card_check_out_now"
        elif direction == "check_in":
            parsed["intent"] = "card_check_in_retro" if parsed.get("time") else "card_check_in_now"
    else:
        from app.assistant_card_intent import correct_card_intent_from_text

        correct_card_intent_from_text(parsed, user_text)
    if str(parsed.get("intent") or "unknown") not in {"unknown", "today_info"} and not str(parsed.get("date") or "").strip():
        parsed["date"] = datetime.now(ZoneInfo("Europe/Athens")).date().isoformat()


def _asks_close_all_open_cards(text: str) -> bool:
    """«κλείσε όλες / όσους / ανοιχτές» χωρίς ρητά ονόματα → λίστα ανοιχτών."""
    folded = _fold_text(text)
    if not any(token in folded for token in ("κλεισ", "close", "checkout", "clockout", "clock out")):
        return False
    return any(
        token in folded
        for token in ("ολεσ", "ολουσ", "οσουσ", "οσα", "ολα", "ανοιχτ", "all")
    )


def _open_checkout_matches_for_date(
    *,
    store_context: dict[str, Any],
    employees: list[dict[str, Any]],
    store_id: int,
    date_iso: str,
) -> list[dict[str, Any]]:
    """Εργαζόμενοι καταστήματος με ανοιχτή κάρτα την ημερομηνία (Αρχική/report)."""
    from app.assistant_home_context import compact_home_employee_row, is_open_home_employee
    from app.card_report import build_card_status_report

    report = build_card_status_report(
        str(store_context.get("employer_afm") or ""),
        str(store_context.get("branch_aa") or "0"),
        date_iso=date_iso,
    )
    open_afms: list[str] = []
    for row in report.get("rows") or []:
        if not isinstance(row, dict):
            continue
        compact = compact_home_employee_row(row)
        if is_open_home_employee(compact):
            afm = str(compact.get("afm") or "").strip()
            if afm:
                open_afms.append(afm)
    open_set = set(open_afms)
    return [
        emp for emp in employees
        if emp.get("store_id") == store_id and str(emp.get("afm") or "").strip() in open_set
    ]


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
    pending_intent = str(parsed.get("pending_intent") or "").strip()
    if (
        intent == "unknown"
        and pending_intent in ALLOWED_INTENTS
        and pending_intent not in {"unknown", *_INFO_INTENTS}
    ):
        intent = pending_intent
        parsed["intent"] = intent
    if intent not in ALLOWED_INTENTS:
        # LLM sometimes invents labels; recover schedule_change from hours.
        hf = str(parsed.get("hour_from") or "")
        ht = str(parsed.get("hour_to") or "")
        if (
            re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", hf)
            and re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", ht)
            and (parsed.get("employee_afms") or parsed.get("employee_afm"))
        ):
            intent = "schedule_change"
            parsed["intent"] = intent
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
    # Name resolution is Gemini's job. Ambiguity is an incomplete field of the
    # existing command; it must not erase the already understood action.
    question = str(parsed.get("clarification_question") or "").strip()
    raw_ambiguous = parsed.get("ambiguous_employee_afms")
    has_ambiguity = isinstance(raw_ambiguous, list) and bool(raw_ambiguous)
    if not has_ambiguity and intent == "unknown" and "εννοειτε" in _fold_text(question):
        raw_ambiguous = afms
        has_ambiguity = bool(raw_ambiguous)
    ambiguous_afms: list[str] = []
    if has_ambiguity:
        for value in raw_ambiguous:
            afm = str(value or "").strip()
            if not afm or afm in ambiguous_afms:
                continue
            if any(emp["store_id"] == store_id and emp["afm"] == afm for emp in employees):
                ambiguous_afms.append(afm)
        if ambiguous_afms:
            parsed["ambiguous_employee_afms"] = ambiguous_afms
            parsed["pending_intent"] = intent if intent not in {"unknown", *_INFO_INTENTS} else pending_intent or None
            parsed["employee_afms"] = []
            parsed["employee_afm"] = None
            afms = []
            matches = []
            errors.append(question or "Χρειάζεται επιλογή εργαζομένου")
    elif intent != "unknown":
        parsed.pop("ambiguous_employee_afms", None)
        parsed.pop("pending_intent", None)
    if (
        intent not in {"unknown", *_INFO_INTENTS}
        and not ambiguous_afms
        and (not afms or len(matches) != len(afms))
        and not (
            intent.startswith("card_check_out")
            and _asks_close_all_open_cards(user_text)
        )
    ):
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
    if intent == "unknown" and not ambiguous_afms:
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

    # «κλείσε όλες» → μόνο πραγματικά ανοιχτές εκείνης της ημέρας (όχι επινόηση LLM).
    if (
        intent.startswith("card_check_out")
        and store_id in allowed_store_ids
        and _is_iso_date(date)
        and not errors
        and _asks_close_all_open_cards(user_text)
    ):
        store_context = next(c for c in contexts if int(c["store_id"]) == store_id)
        matches = _open_checkout_matches_for_date(
            store_context=store_context,
            employees=employees,
            store_id=int(store_id),
            date_iso=date,
        )
        afms = [str(item.get("afm") or "") for item in matches if str(item.get("afm") or "")]
        parsed["employee_afms"] = afms
        parsed["employee_afm"] = afms[0] if len(afms) == 1 else None
        if not matches:
            errors.append(
                "Δεν υπάρχουν ανοιχτές κάρτες για κλείσιμο αυτή την ημερομηνία"
            )

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
            if not reason:
                eligible_matches.append(match)
                continue
            label = f"{match.get('name') or afm}: {reason}"
            # Soft skips: already open/closed / no entry — continue with others.
            # Hard errors (e.g. future time): block as clarification.
            soft = reason.startswith("Δεν γίνεται ")
            if soft:
                skipped_card.append(label)
            else:
                errors.append(label)
        if errors:
            pass
        elif eligible_matches:
            matches = eligible_matches
            afms = [str(item.get("afm") or "") for item in matches if str(item.get("afm") or "")]
            parsed["employee_afms"] = afms
            parsed["employee_afm"] = afms[0] if len(afms) == 1 else None
            if skipped_card:
                parsed["skipped_card_employees"] = skipped_card
        elif skipped_card:
            # Everyone soft-skipped — inform, do not ask clarification.
            matches = []
            afms = []
            parsed["employee_afms"] = []
            parsed["employee_afm"] = None
            parsed["skipped_card_employees"] = skipped_card
            parsed["card_action_all_skipped"] = True
        else:
            errors.append("Κανένας εργαζόμενος δεν είναι επιλέξιμος για αυτή την ενέργεια κάρτας")

    validation = {"valid": not errors, "errors": errors, "execution_enabled": False}
    if errors:
        status = "needs_clarification"
    elif intent in _INFO_INTENTS or parsed.get("card_action_all_skipped"):
        status = "answered"
    else:
        status = "draft"
    if matches:
        names = ", ".join(str(match.get("name") or match.get("afm") or "εργαζόμενος") for match in matches)
    else:
        references = parsed.get("employee_references")
        if not isinstance(references, list):
            references = [parsed.get("employee_reference")] if parsed.get("employee_reference") else []
        names = ", ".join(str(value).strip() for value in references if str(value or "").strip()) or "εργαζόμενος"
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
        "cancel_pending": "Ακύρωση εντολής",
        "unknown": "Μη αναγνωρισμένη εντολή",
    }
    if intent == "today_info":
        proposed = str(parsed.get("clarification_question") or "").strip()
    elif intent == "cancel_pending":
        proposed = str(parsed.get("clarification_question") or "Ακυρώθηκε η εντολή.").strip()
    elif parsed.get("card_action_all_skipped"):
        action_noun = "άνοιγμα" if "check_in" in intent else "κλείσιμο"
        if len(skipped_card) == 1:
            proposed = skipped_card[0]
        else:
            proposed = (
                f"Δεν είναι δυνατό το {action_noun} κάρτας:\n"
                + "\n".join(f"• {item}" for item in skipped_card)
            )
    elif intent in {"card_check_in_schedule", "card_check_out_schedule"} and matches:
        proposed = "\n".join(
            f"{match.get('name') or match.get('afm')} · {display_date} · {labels[intent]} {schedule_times.get(str(match.get('afm') or ''), '—')}"
            for match in matches
        )
    else:
        proposed = f"{names} · {display_date} · {labels[intent]}"
    if skipped_card and not parsed.get("card_action_all_skipped"):
        proposed += "\nΠαραλείφθηκαν:\n" + "\n".join(f"• {item}" for item in skipped_card)
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
