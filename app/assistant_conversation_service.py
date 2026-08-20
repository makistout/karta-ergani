"""Channel-neutral AI assistant parsing and task creation."""

from __future__ import annotations

import re
import unicodedata
from typing import Any


def _fold(text: str) -> str:
    normalized = unicodedata.normalize("NFD", str(text or ""))
    stripped = "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")
    return re.sub(r"\s+", " ", stripped.casefold()).strip()


def _is_affirmative(text: str) -> bool:
    folded = _fold(text)
    if not folded:
        return False
    tokens = {
        "ναι", "ναι.", "ναι!", "yes", "y", "ok", "οκ", "okay", "σωστα", "βεβαια",
        "ακυρωσε", "ακυρωση", "ακυρωστε",
    }
    if folded in tokens:
        return True
    if folded.startswith("ναι ") or folded.startswith("yes "):
        return True
    if "ακυρωσ" in folded and any(part in folded for part in ("ναι", "yes", "οκ", "ok")):
        return True
    return False


def _is_negative(text: str) -> bool:
    folded = _fold(text)
    if not folded:
        return False
    if folded in {"οχι", "οχι.", "no", "n", "μη", "μην"}:
        return True
    return folded.startswith("οχι ") or folded.startswith("no ")


def _offers_cancel(text: str) -> bool:
    folded = _fold(text)
    return "ακυρ" in folded or "cancel" in folded


def _clarification_question_text(pending: dict[str, Any]) -> str:
    return str(
        pending.get("clarification_text")
        or pending.get("proposed_action_text")
        or ""
    ).strip()


def _pending_employee_context(pending: dict[str, Any]) -> dict[str, Any]:
    payload = pending.get("payload") if isinstance(pending.get("payload"), dict) else {}
    afms = payload.get("employee_afms")
    if not isinstance(afms, list):
        afms = [payload.get("employee_afm")] if payload.get("employee_afm") else []
    afms = [str(value).strip() for value in afms if str(value or "").strip()]
    return {
        "store_id": pending.get("store_id") or payload.get("store_id"),
        "employee_afm": afms[0] if len(afms) == 1 else payload.get("employee_afm"),
        "employee_afms": afms,
        "message_text": _clarification_question_text(pending),
        "focus_locked": True,
        "pending_clarification_task_id": pending.get("id"),
    }


def _result(
    *,
    task_id: int,
    status: str,
    task_status: str,
    answer: str,
    parsed: dict[str, Any] | None = None,
    validation: dict[str, Any] | None = None,
    proposed: str = "",
    recipient_id: int | None = None,
) -> dict[str, Any]:
    return {
        "task_id": task_id,
        "status": status,
        "task_status": task_status,
        "answer": answer,
        "parsed": parsed or {},
        "validation": validation or {"valid": True, "errors": [], "execution_enabled": False},
        "proposed": proposed,
        "recipient_id": recipient_id,
    }


def _resolve_pending_clarification(
    pending: dict[str, Any],
    *,
    text: str,
    contexts: list[dict[str, Any]],
    inbound_id: int,
    confirmation_mode: str,
    reply_context: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Bind a user answer to an open clarification instead of opening a new command."""
    from app.repo_telegram_assistant import (
        cancel_assistant_task,
        mark_inbound,
        update_assistant_task,
    )
    from app.telegram_assistant_service import parse_command, validate_and_describe

    task_id = int(pending["id"])
    question = _clarification_question_text(pending)
    recipient_id = pending.get("recipient_id")

    # Only when the system itself asked «να ακυρώσω;» and user says ναι/ok.
    if _offers_cancel(question) and _is_affirmative(text):
        cancel_assistant_task(task_id, reason="user_cancelled_clarification")
        mark_inbound(inbound_id, "clarification_cancelled")
        answer = (
            f"Ακυρώθηκε η εντολή #{task_id}. "
            "Δεν έγινε καμία αποστολή στο ΕΡΓΑΝΗ."
        )
        return _result(
            task_id=task_id,
            status="answered",
            task_status="cancelled",
            answer=answer,
            parsed=pending.get("payload") if isinstance(pending.get("payload"), dict) else {},
            proposed=answer,
            recipient_id=recipient_id,
        )

    if _offers_cancel(question) and _is_negative(text):
        mark_inbound(inbound_id, "clarification_continued")
        answer = (
            f"Η εντολή #{task_id} παραμένει ανοιχτή.\n"
            "Πείτε μου τι ενέργεια θέλετε για τους ίδιους εργαζομένους "
            "(π.χ. άνοιγμα/κλείσιμο κάρτας, ρεπό, άδεια)."
        )
        return _result(
            task_id=task_id,
            status="needs_clarification",
            task_status="needs_clarification",
            answer=answer,
            parsed=pending.get("payload") if isinstance(pending.get("payload"), dict) else {},
            validation={"valid": False, "errors": ["Αναμένεται ενέργεια για τους εργαζομένους"], "execution_enabled": False},
            proposed=answer,
            recipient_id=recipient_id,
        )

    payload = dict(pending.get("payload") or {}) if isinstance(pending.get("payload"), dict) else {}
    folded_question = _fold(question)

    # User answer goes to Gemini as-is. Context carries the open question + candidates.
    focus = _pending_employee_context(pending)
    merged_reply = dict(reply_context or {})
    merged_reply.update({k: v for k, v in focus.items() if v not in (None, [], "")})
    # Do not mine AFMs from the clarification question (it lists every candidate).
    merged_reply.pop("employee_afms", None)
    merged_reply.pop("employee_afm", None)
    merged_reply["message_text"] = question
    merged_reply["pending_clarification_task_id"] = task_id

    if "εννοειτε" in folded_question:
        from app.telegram_assistant_service import _employee_catalog

        employees_catalog = _employee_catalog(contexts)
        store_id = pending.get("store_id") or payload.get("store_id")
        try:
            store_id = int(store_id) if store_id is not None else None
        except (TypeError, ValueError):
            store_id = None
        raw_candidates = payload.get("ambiguous_employee_afms")
        candidate_afms = [
            str(afm).strip()
            for afm in (raw_candidates if isinstance(raw_candidates, list) else [])
            if str(afm or "").strip()
        ]
        allowed = set(candidate_afms)
        candidates = [
            {
                "afm": str(emp.get("afm") or "").strip(),
                "name": str(emp.get("name") or "").strip(),
                "store_id": emp.get("store_id"),
            }
            for emp in employees_catalog
            if (store_id is None or emp.get("store_id") == store_id)
            and str(emp.get("afm") or "").strip()
            and (not allowed or str(emp.get("afm") or "").strip() in allowed)
        ]
        if allowed:
            candidates = [row for row in candidates if row["afm"] in allowed]
        else:
            candidates = []
        merged_reply["pending_clarification"] = {
            "kind": "name_choice",
            "task_id": task_id,
            "question": question,
            "candidate_afms": candidate_afms,
            "candidate_employees": candidates[:20],
            "preserve_intent": payload.get("intent"),
            "preserve_date": payload.get("date"),
            "preserve_time": payload.get("time"),
            "preserve_store_id": payload.get("store_id") or store_id,
            "preserve_hour_from": payload.get("hour_from"),
            "preserve_hour_to": payload.get("hour_to"),
            "preserve_leave_type": payload.get("leave_type"),
        }
    else:
        merged_reply["pending_clarification"] = {
            "kind": "generic",
            "task_id": task_id,
            "question": question,
            "preserve_intent": payload.get("intent"),
            "preserve_date": payload.get("date"),
            "preserve_store_id": payload.get("store_id"),
            "preserve_employee_afms": payload.get("employee_afms"),
        }

    # Critical: send the user's raw answer — do not wrap / rephrase / stem it.
    parsed, employees, llm_metadata = parse_command(
        text=text, contexts=contexts, reply_context=merged_reply,
    )
    if isinstance(parsed, dict) and str(parsed.get("intent") or "") == "cancel_pending":
        cancel_assistant_task(task_id, reason="user_cancelled")
        mark_inbound(inbound_id, "user_cancelled")
        answer = (
            f"Ακυρώθηκε η εντολή #{task_id}. "
            "Δεν έγινε καμία αποστολή στο ΕΡΓΑΝΗ."
        )
        return _result(
            task_id=task_id,
            status="answered",
            task_status="cancelled",
            answer=answer,
            parsed=parsed,
            proposed=answer,
            recipient_id=recipient_id,
        )

    if isinstance(parsed, dict):
        preserve = merged_reply.get("pending_clarification") or {}
        if str(parsed.get("intent") or "unknown") == "unknown" and preserve.get("preserve_intent"):
            parsed["intent"] = preserve["preserve_intent"]
        for key, preserve_key in (
            ("date", "preserve_date"),
            ("time", "preserve_time"),
            ("store_id", "preserve_store_id"),
            ("hour_from", "preserve_hour_from"),
            ("hour_to", "preserve_hour_to"),
            ("leave_type", "preserve_leave_type"),
        ):
            if not parsed.get(key) and preserve.get(preserve_key) not in (None, ""):
                parsed[key] = preserve[preserve_key]
        if preserve.get("kind") == "name_choice":
            parsed.pop("ambiguous_employee_afms", None)

    status, validation, proposed = validate_and_describe(
        parsed, contexts=contexts, employees=employees,
        reply_context=merged_reply, user_text=text,
    )
    task_status = (
        ("awaiting_ui_confirmation" if confirmation_mode == "ui" else "awaiting_pin")
        if status == "draft" else status
    )
    update_assistant_task(
        task_id,
        parsed=parsed,
        status=task_status,
        validation=validation,
        proposed_action=proposed,
        llm_metadata=llm_metadata,
    )
    mark_inbound(inbound_id, "clarification_reply")
    if status == "draft":
        answer = f"Εντολή #{task_id}:\n{proposed}"
    elif status == "answered":
        answer = proposed
    else:
        problems = "\n".join(f"• {item}" for item in validation.get("errors") or [])
        answer = f"Η εντολή #{task_id} χρειάζεται διευκρίνιση:\n{problems}\n\nΔεν έγινε καμία αποστολή στο ΕΡΓΑΝΗ."
    return _result(
        task_id=task_id,
        status=status,
        task_status=task_status,
        answer=answer,
        parsed=parsed,
        validation=validation,
        proposed=proposed,
        recipient_id=recipient_id,
    )


def process_assistant_command(
    *, text: str, contexts: list[dict[str, Any]], inbound_id: int,
    recipient_id: int | None = None, store_id: int | None = None,
    reply_context: dict[str, Any] | None = None, confirmation_mode: str = "pin",
    office_user: str | None = None, chat_id: str | None = None,
) -> dict[str, Any]:
    from app.repo_telegram_assistant import (
        create_task,
        latest_pending_clarification,
        mark_inbound,
    )
    from app.telegram_assistant_service import parse_command, validate_and_describe

    pending = latest_pending_clarification(
        store_id=store_id,
        office_user=office_user,
        chat_id=None if office_user else chat_id,
    )
    if pending:
        resolved = _resolve_pending_clarification(
            pending,
            text=text,
            contexts=contexts,
            inbound_id=inbound_id,
            confirmation_mode=confirmation_mode,
            reply_context=reply_context,
        )
        if resolved is not None:
            return resolved

    parsed, employees, llm_metadata = parse_command(
        text=text, contexts=contexts, reply_context=dict(reply_context or {}),
    )
    status, validation, proposed = validate_and_describe(
        parsed, contexts=contexts, employees=employees,
        reply_context=dict(reply_context or {}), user_text=text,
    )
    store_ids = {int(row["store_id"]) for row in contexts}
    selected_store = parsed.get("store_id")
    selected_recipient = next(
        (int(c["recipient_id"]) for c in contexts
         if c.get("recipient_id") is not None and int(c["store_id"]) == selected_store),
        recipient_id,
    )
    task_status = (
        ("awaiting_ui_confirmation" if confirmation_mode == "ui" else "awaiting_pin")
        if status == "draft" else status
    )
    task_id = create_task(
        inbound_id=inbound_id,
        recipient_id=selected_recipient,
        store_id=int(selected_store) if selected_store in store_ids else store_id,
        parsed=parsed,
        status=task_status,
        validation=validation,
        proposed_action=proposed,
        llm_metadata=llm_metadata,
    )
    mark_inbound(inbound_id, "parsed")
    if status == "draft":
        answer = f"Εντολή #{task_id}:\n{proposed}"
    elif status == "answered":
        answer = proposed
    else:
        problems = "\n".join(f"• {item}" for item in validation.get("errors") or [])
        answer = f"Η εντολή #{task_id} χρειάζεται διευκρίνιση:\n{problems}\n\nΔεν έγινε καμία αποστολή στο ΕΡΓΑΝΗ."
    return {
        "task_id": task_id, "status": status, "task_status": task_status,
        "answer": answer, "parsed": parsed, "validation": validation,
        "proposed": proposed, "recipient_id": selected_recipient,
    }
