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
    reset_conversation_focus: bool = False,
) -> dict[str, Any]:
    payload = dict(parsed or {})
    if reset_conversation_focus:
        payload["employee_afms"] = []
        payload["employee_afm"] = None
        payload.pop("ambiguous_employee_afms", None)
    return {
        "task_id": task_id,
        "status": status,
        "task_status": task_status,
        "answer": answer,
        "parsed": payload,
        "validation": validation or {"valid": True, "errors": [], "execution_enabled": False},
        "proposed": proposed,
        "recipient_id": recipient_id,
        "reset_conversation_focus": bool(reset_conversation_focus),
    }


def _cancelled_answer(task_id: int | None = None, *, cancelled_ids: list[int] | None = None) -> str:
    ids = [int(value) for value in (cancelled_ids or []) if value]
    if task_id and int(task_id) not in ids:
        ids = [int(task_id), *ids]
    if len(ids) > 1:
        listed = ", ".join(f"#{item}" for item in ids)
        return (
            f"Ακυρώθηκαν οι ανοιχτές εντολές {listed}. "
            "Δεν έγινε καμία αποστολή στο ΕΡΓΑΝΗ. "
            "Μπορείτε να δώσετε νέα εντολή από την αρχή."
        )
    if ids:
        return (
            f"Ακυρώθηκε η εντολή #{ids[0]}. "
            "Δεν έγινε καμία αποστολή στο ΕΡΓΑΝΗ. "
            "Μπορείτε να δώσετε νέα εντολή από την αρχή."
        )
    return (
        "Ακυρώθηκε η ανοιχτή εντολή. "
        "Δεν έγινε καμία αποστολή στο ΕΡΓΑΝΗ. "
        "Μπορείτε να δώσετε νέα εντολή από την αρχή."
    )


def _resolve_pending_clarification(
    pending: dict[str, Any],
    *,
    text: str,
    contexts: list[dict[str, Any]],
    inbound_id: int,
    confirmation_mode: str,
    reply_context: dict[str, Any] | None,
) -> dict[str, Any] | None:
    """Bind every user reply to the current non-terminal command."""
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
        answer = _cancelled_answer(task_id)
        return _result(
            task_id=task_id,
            status="answered",
            task_status="cancelled",
            answer=answer,
            parsed=pending.get("payload") if isinstance(pending.get("payload"), dict) else {},
            proposed=answer,
            recipient_id=recipient_id,
            reset_conversation_focus=True,
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
            "original_message": pending.get("original_message_text"),
            "candidate_afms": candidate_afms,
            "candidate_employees": candidates[:20],
            "preserve_intent": payload.get("pending_intent") or payload.get("intent"),
            "preserve_date": payload.get("date"),
            "preserve_time": payload.get("time"),
            "preserve_store_id": payload.get("store_id") or store_id,
            "preserve_hour_from": payload.get("hour_from"),
            "preserve_hour_to": payload.get("hour_to"),
            "preserve_leave_type": payload.get("leave_type"),
        }
    else:
        merged_reply["pending_clarification"] = {
            "kind": (
                "command_revision"
                if str(pending.get("task_status") or "") in {"awaiting_ui_confirmation", "awaiting_pin"}
                else "generic"
            ),
            "task_id": task_id,
            "question": question,
            "original_message": pending.get("original_message_text"),
            "preserve_intent": payload.get("intent"),
            "preserve_date": payload.get("date"),
            "preserve_time": payload.get("time"),
            "preserve_store_id": payload.get("store_id"),
            "preserve_employee_afms": payload.get("employee_afms"),
            "preserve_hour_from": payload.get("hour_from"),
            "preserve_hour_to": payload.get("hour_to"),
            "preserve_leave_type": payload.get("leave_type"),
        }

    # Critical: send the user's raw answer — do not wrap / rephrase / stem it.
    parsed, employees, llm_metadata = parse_command(
        text=text, contexts=contexts, reply_context=merged_reply,
    )
    if isinstance(parsed, dict) and str(parsed.get("intent") or "") == "cancel_pending":
        cancel_assistant_task(task_id, reason="user_cancelled")
        mark_inbound(inbound_id, "user_cancelled")
        answer = _cancelled_answer(task_id)
        return _result(
            task_id=task_id,
            status="answered",
            task_status="cancelled",
            answer=answer,
            parsed=parsed,
            proposed=answer,
            recipient_id=recipient_id,
            reset_conversation_focus=True,
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
        if not parsed.get("employee_afms") and preserve.get("preserve_employee_afms"):
            parsed["employee_afms"] = list(preserve["preserve_employee_afms"])
            parsed["employee_afm"] = (
                parsed["employee_afms"][0] if len(parsed["employee_afms"]) == 1 else None
            )
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
        cancel_open_assistant_tasks,
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

    # Fresh cancel (e.g. «άκυρο» while a draft awaits confirmation): close opens + reset focus.
    if str(parsed.get("intent") or "") == "cancel_pending":
        cancelled_ids = cancel_open_assistant_tasks(
            store_id=store_id,
            office_user=office_user,
            chat_id=None if office_user else chat_id,
            reason="user_cancelled",
        )
        mark_inbound(inbound_id, "user_cancelled")
        # Newest first (ORDER BY id DESC) — cite the command the user just saw.
        primary = cancelled_ids[0] if cancelled_ids else 0
        if primary:
            answer = _cancelled_answer(primary, cancelled_ids=cancelled_ids)
            task_id = primary
        else:
            # No open task — still acknowledge and clear focus.
            task_id = create_task(
                inbound_id=inbound_id,
                recipient_id=recipient_id,
                store_id=store_id,
                parsed={"intent": "cancel_pending", "employee_afms": [], "confidence": 1.0},
                status="cancelled",
                validation={"valid": True, "errors": [], "execution_enabled": False},
                proposed_action=_cancelled_answer(),
                llm_metadata=llm_metadata,
            )
            answer = _cancelled_answer()
        return _result(
            task_id=task_id,
            status="answered",
            task_status="cancelled",
            answer=answer,
            parsed={"intent": "cancel_pending", "employee_afms": [], "store_id": store_id},
            proposed=answer,
            recipient_id=recipient_id,
            reset_conversation_focus=True,
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
        "reset_conversation_focus": False,
    }
