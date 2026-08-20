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


def _needs_today_home(text: str, reply_context: dict[str, Any] | None) -> bool:
    """Skip building/sending today_home unless the message likely needs it."""
    ctx = dict(reply_context or {})
    pending = ctx.get("pending_clarification")
    if isinstance(pending, dict) and pending.get("kind") == "name_choice":
        return False
    folded = _fold_text(text)
    if not folded:
        return False
    needles = (
        "ποιοι", "ποιος", "ποια", "τι ωρα",
        "τελειων", "αρχιζ", "οσοι", "οσους", "οσες",
        "ολους ", "ολες ", "ανοιχτ", "σε εργασια", "στη δουλεια",
        "ποιος εχει", "εικον εργασ", "χτυπημ",
        "οσοι τελειων", "οσους τελειων",
    )
    return any(needle in folded for needle in needles)


def _assistant_prompt_guide() -> list[str]:
    """Compact, non-duplicated guidance (token-cheap). Examples are non-binding."""
    return [
        "Parser εντολών erganiOS (όχι chatbot). Ελληνικά/greeklish → JSON. Μην γράφεις meta («το διορθώνω»).",
        "Μόνο store_id/ΑΦΜ από allowed_*. Ονόματα φωνητικά (dionisi→ΔΙΟΝΥΣΙΟΣ, fotopoulou→ΦΩΤΟΠΟΥΛΟΣ). Greeklish=ελληνικά.",
        "Ίδια/παρόμοια επώνυμα χωρίς διακριτό όνομα → unknown + «Εννοείτε του Χ ή του Υ;» (όλες οι επιλογές, άρθρο φύλου).",
        "pending_clarification.name_choice: το message είναι η απάντηση ως έχει· ένα ΑΦΜ από candidate_*· κληρονόμησε preserve_*.",
        "Ακύρωση/απόρριψη οποιασδήποτε διατύπωσης (ακύρωσε, άστο, γάμα το, μην το κάνεις, #N…) → cancel_pending. Όχι whitelist.",
        "Κάρτα χωρίς ώρα («άνοιξε/κλείσε κάρτα») = *_now, time=null. «πριν 10 λεπτά» = *_retro από now. «στις 10» = *_retro ακριβώς. Μην μαντεύεις ώρα.",
        "Πολλές εντολές/εργαζόμενοι OK. Ίδια ενέργεια+ημερομηνία+ώρα → μία εγγραφή commands με πολλά employee_afms.",
        "today_home μόνο σήμερα· για today_info / ομαδικά («όσους τελειώνουν…»). Αν today_home απόν, μην επινοείς εικόνα εργασίας.",
        "Έξοδος: μόνο ανοιχτές κάρτες. Είσοδος: χωρίς ήδη είσοδο. *_now: at_work/needs_checkout ή needs_checkin/late_arrival.",
        "Βάσει ωραρίου → *_schedule χωρίς ώρα. Ρεπό=rest_day. Άδεια=leave+leave_type. Ωράριο=hour_from/hour_to.",
        "conversation_focus/reply_context κληρονομούνται σε σύντομες απαντήσεις. Ώρες 17.00→17:00. Ασαφές→unknown+clarification_question.",
    ]


def parse_command(
    *, text: str, contexts: list[dict[str, Any]], reply_context: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    if not Config.GEMINI_API_KEY:
        raise RuntimeError("Δεν έχει ρυθμιστεί GEMINI_API_KEY")
    now = datetime.now(ZoneInfo("Europe/Athens"))
    employees = _employee_catalog(contexts)
    stores = [
        {"id": int(c["store_id"]), "name": str(c.get("store_name") or "")}
        for c in contexts
    ]

    # If we can resolve a single store from focus/reply/text, narrow employees & today_home
    focus = _conversation_focus(reply_context, contexts=contexts, employees=employees)
    focused_store_id: int | None = None
    if focus.get("store_id") and int(focus["store_id"]) in {int(c["store_id"]) for c in contexts}:
        focused_store_id = int(focus["store_id"])
    if not focused_store_id:
        mentioned = _mentioned_store_ids(text, contexts)
        if len(mentioned) == 1:
            focused_store_id = mentioned[0]
    if focused_store_id:
        employees = [e for e in employees if e["store_id"] == focused_store_id]

    include_home = _needs_today_home(text, reply_context)
    today_home: dict[str, Any] | None = None
    if include_home:
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
    }
    if today_home is not None:
        prompt["today_home"] = today_home
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
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    # Greek casefold maps capital Σ to final ς; normalize to σ for matching.
    return text.replace("ς", "σ")


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


def _is_female_name(first_name: str, surname: str = "") -> bool:
    first = _fold_text(first_name)
    if first.endswith(("α", "η", "ω")) or first.endswith(_fold_text("ου")):
        if not (
            first.endswith(_fold_text("ας"))
            or first.endswith(_fold_text("ης"))
            or first.endswith(_fold_text("ος"))
        ):
            return True
    female_tokens = {
        "ελενη", "μαρια", "αικατερινη", "σοφια", "αννα", "ευα", "ιωαννα", "χριστινα",
        "γεωργια", "δημητρα", "παρασκευη", "βασιλικη", "αλεξανδρα", "ολγα", "ειρηνη",
    }
    return first in female_tokens


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


def _choice_label(employee: dict[str, Any]) -> str:
    surname, first = _name_parts(employee)
    article = "της" if _is_female_name(first, surname) else "του"
    first_gen = _genitive_first_name(first) or str(employee.get("name") or employee.get("afm") or "").upper()
    return f"{article} {first_gen.title()}"


def _format_name_choices(candidates: list[dict[str, Any]]) -> str:
    labels = [_choice_label(item) for item in candidates]
    labels = [label for label in labels if label.strip()]
    if not labels:
        return "Παρακαλώ διευκρινίστε ποιο άτομο εννοείτε."
    if len(labels) == 1:
        return f"Εννοείτε {labels[0]};"
    if len(labels) == 2:
        return f"Εννοείτε {labels[0]} ή {labels[1]};"
    return f"Εννοείτε {', '.join(labels[:-1])} ή {labels[-1]};"


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


def _singular_person_request(text: str) -> bool:
    folded = f" {_fold_text(text)} "
    if any(hint in folded for hint in _GROUP_FOCUS_HINTS):
        return False
    singular_markers = (
        " του ", " της ", " τον ", " την ", " τον/την ",
        " την καρτα ", " την κάρτα ", " τον καρτα ",
    )
    # Markers already folded, so κάρτα → καρτα
    singular_markers = (
        " του ", " της ", " τον ", " την ",
        " την καρτα ", " τον καρτα ",
    )
    return any(marker in folded for marker in singular_markers)


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


def _ambiguous_name_candidates(
    text: str,
    employees: list[dict[str, Any]],
    store_id: int | None,
    selected_afms: list[str] | None = None,
) -> list[dict[str, Any]]:
    """Return near-duplicate employees when a surname query is not unique."""
    pool = [
        emp for emp in employees
        if store_id is None or emp.get("store_id") == store_id
    ]
    tokens = _query_tokens(text)
    selected = {str(afm).strip() for afm in (selected_afms or []) if str(afm or "").strip()}
    candidates: list[dict[str, Any]] = []

    def add(emp: dict[str, Any]) -> None:
        afm = str(emp.get("afm") or "").strip()
        if not afm:
            return
        if any(str(item.get("afm") or "") == afm for item in candidates):
            return
        candidates.append(emp)

    for emp in pool:
        surname, first = _name_parts(emp)
        if not surname:
            continue
        for token in tokens:
            if _employee_surname_matches_token(surname, token):
                add(emp)
                break
            if first and _fold_text(first) == _fold_text(token):
                add(emp)
                break

    # Expand selected people with same/similar surname siblings.
    for emp in pool:
        afm = str(emp.get("afm") or "").strip()
        if afm not in selected:
            continue
        surname, _ = _name_parts(emp)
        stem = _surname_stem(surname)
        for other in pool:
            other_surname, _ = _name_parts(other)
            if _stems_similar(stem, _surname_stem(other_surname)):
                add(other)

    if len(candidates) < 2:
        return []

    # If the user already named a unique first name among candidates, no ambiguity.
    named = [
        emp for emp in candidates
        if _first_name_in_text(text, _name_parts(emp)[1])
    ]
    if len(named) == 1:
        return []

    # Same exact surname (VLASENKO/VLASENKO) always clarify when singular.
    surname_groups: dict[str, list[dict[str, Any]]] = {}
    for emp in candidates:
        key = _fold_text(_name_parts(emp)[0])
        surname_groups.setdefault(key, []).append(emp)
    exact_dupes = [group for group in surname_groups.values() if len(group) >= 2]
    if exact_dupes:
        return sorted(
            [emp for group in exact_dupes for emp in group],
            key=lambda item: str(item.get("name") or ""),
        )

    if _singular_person_request(text) or len(selected) <= 1:
        return sorted(candidates, key=lambda item: str(item.get("name") or ""))
    return []


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
    hits = list(dict.fromkeys(value for value in hits if value))
    named_hits = []
    for emp in employees:
        if store_id is not None and emp.get("store_id") != store_id:
            continue
        afm = str(emp.get("afm") or "").strip()
        if afm not in hits:
            continue
        _, first = _name_parts(emp)
        if _first_name_in_text(raw, first):
            named_hits.append(afm)
    if len(set(named_hits)) == 1:
        return [named_hits[0]]
    ambiguous = _ambiguous_name_candidates(text, employees, store_id, hits)
    if ambiguous:
        # Keep all near-matches so validation can ask for a full choice list.
        return [str(emp.get("afm") or "").strip() for emp in ambiguous if emp.get("afm")]
    return hits


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
    pending_clarification = {}
    if isinstance(reply_context, dict):
        pending_clarification = reply_context.get("pending_clarification") or {}
        if not isinstance(pending_clarification, dict):
            pending_clarification = {}
    mentioned_afms = _mentioned_afms(user_text, employees, store_id if store_id in allowed_store_ids else None)
    group_query = any(hint in str(user_text or "").casefold() for hint in _GROUP_FOCUS_HINTS)
    # Name-choice answers: trust the LLM pick; do not re-inherit both candidates
    # from the clarification question text sitting in conversation_focus.
    if pending_clarification.get("kind") == "name_choice" and parsed_afms:
        afms = parsed_afms
    elif mentioned_afms:
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
    pending_clarification = {}
    if isinstance(reply_context, dict):
        pending_clarification = reply_context.get("pending_clarification") or {}
        if not isinstance(pending_clarification, dict):
            pending_clarification = {}
    candidate_afms = {
        str(afm).strip()
        for afm in (pending_clarification.get("candidate_afms") or [])
        if str(afm or "").strip()
    }
    name_choice_resolved = (
        pending_clarification.get("kind") == "name_choice"
        and len(afms) == 1
        and (not candidate_afms or afms[0] in candidate_afms)
    )
    ambiguous = [] if name_choice_resolved else _ambiguous_name_candidates(
        user_text, employees, store_id, afms,
    )
    if intent not in {"unknown", *_INFO_INTENTS} and len(ambiguous) >= 2:
        named_unique = [
            emp for emp in ambiguous
            if _first_name_in_text(user_text, _name_parts(emp)[1])
        ]
        if len(named_unique) != 1:
            errors.append(_format_name_choices(ambiguous))
            parsed["ambiguous_employee_afms"] = [
                str(emp.get("afm") or "").strip() for emp in ambiguous if emp.get("afm")
            ]
            parsed["employee_afms"] = []
            parsed["employee_afm"] = None
            matches = []
            afms = []
        else:
            afms = [str(named_unique[0].get("afm") or "").strip()]
            parsed["employee_afms"] = afms
            parsed["employee_afm"] = afms[0]
            matches = named_unique
            parsed.pop("ambiguous_employee_afms", None)
    if name_choice_resolved:
        parsed.pop("ambiguous_employee_afms", None)
    if intent not in {"unknown", *_INFO_INTENTS} and (not afms or len(matches) != len(afms)):
        if not any("Εννοείτε " in item for item in errors):
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
        "cancel_pending": "Ακύρωση εντολής",
        "unknown": "Μη αναγνωρισμένη εντολή",
    }
    if intent == "today_info":
        proposed = str(parsed.get("clarification_question") or "").strip()
    elif intent == "cancel_pending":
        proposed = str(parsed.get("clarification_question") or "Ακυρώθηκε η εντολή.").strip()
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
