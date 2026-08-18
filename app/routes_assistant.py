"""Authenticated UI channel for the shared AI assistant conversation."""

from __future__ import annotations

from flask import Blueprint, jsonify, request, session

from app.access_control import can_access_store
from app.assistant_messages import ai_agent_disabled_message
from app.audit_log import record_audit_event
from app.office_auth import SESSION_USER
from app.repo_store import get_action_settings, get_store_config

assistant_bp = Blueprint("assistant", __name__, url_prefix="/api/assistant")


def _user() -> str:
    return str(session.get(SESSION_USER) or "").strip()


def _context(store: dict) -> dict:
    return {
        "recipient_id": None, "store_id": int(store["id"]),
        "store_name": store.get("name"), "employer_afm": store.get("employer_afm"),
        "branch_aa": store.get("branch_aa"), "ai_agent_enabled": store.get("ai_agent_enabled", 0),
    }


@assistant_bp.get("/history/<int:store_id>")
def history(store_id: int):
    if not can_access_store(store_id):
        return jsonify({"error": "Δεν έχετε πρόσβαση σε αυτό το κατάστημα"}), 403
    from app.repo_telegram_assistant import list_conversation_history
    return jsonify({"messages": list_conversation_history(store_id=store_id, office_user=_user())})


@assistant_bp.post("/message")
def message():
    data = request.get_json(silent=True) or {}
    store_id = int(data.get("store_id") or 0)
    text = str(data.get("text") or "").strip()
    if not store_id or not text:
        return jsonify({"error": "Λείπει κατάστημα ή μήνυμα"}), 400
    if not can_access_store(store_id):
        return jsonify({"error": "Δεν έχετε πρόσβαση σε αυτό το κατάστημα"}), 403
    store = get_store_config(store_id)
    if not store:
        return jsonify({"error": "Δεν βρέθηκε κατάστημα"}), 404
    store["ai_agent_enabled"] = bool(get_action_settings(store_id).get("ai_agent_enabled"))
    from app.repo_telegram_assistant import create_ui_inbound_message, mark_inbound, record_ui_outbound_message
    if not store["ai_agent_enabled"]:
        answer = ai_agent_disabled_message()
        inbound_id = create_ui_inbound_message(
            office_user=_user(), store_id=store_id, text=text,
            raw_payload={"source": "ui", "path": request.path, "disabled": True},
        )
        record_ui_outbound_message(
            office_user=_user(), store_id=store_id, text=answer,
            context={"notification_type": "assistant_disabled", "notification_reference_id": str(inbound_id)},
        )
        mark_inbound(inbound_id, "disabled")
        record_audit_event(action="assistant.message", success=False, http_status=403,
                           entity_type="assistant_message", entity_id=str(inbound_id),
                           details={"channel": "ui", "store_id": store_id, "reason": "ai_agent_disabled"})
        return jsonify({"success": True, "answer": answer, "disabled": True})
    from app.assistant_conversation_service import process_assistant_command
    inbound_id = create_ui_inbound_message(
        office_user=_user(), store_id=store_id, text=text,
        raw_payload={"source": "ui", "path": request.path},
    )
    try:
        result = process_assistant_command(
            text=text, contexts=[_context(store)], inbound_id=inbound_id,
            store_id=store_id, confirmation_mode="ui",
        )
        record_ui_outbound_message(
            office_user=_user(), store_id=store_id, text=result["answer"],
            context={"notification_type": "assistant_reply", "notification_reference_id": str(result["task_id"]),
                     "employee_afm": result["parsed"].get("employee_afm")},
        )
        record_audit_event(action="assistant.message", success=True, entity_type="assistant_task",
                           entity_id=str(result["task_id"]), details={"channel": "ui", "store_id": store_id})
        return jsonify({"success": True, **result})
    except Exception as ex:
        mark_inbound(inbound_id, "failed", str(ex))
        if "GEMINI_API_KEY" in str(ex):
            answer = (
                "Ο AI Agent δεν μπορεί να αναλύσει την εντολή, επειδή δεν έχει "
                "ρυθμιστεί το GEMINI_API_KEY στον server. Δεν έγινε καμία αποστολή στο ΕΡΓΑΝΗ."
            )
        else:
            answer = "Δεν μπόρεσα να αναλύσω την εντολή. Δεν έγινε καμία αποστολή στο ΕΡΓΑΝΗ."
        try:
            record_ui_outbound_message(
                office_user=_user(), store_id=store_id, text=answer,
                context={"notification_type": "assistant_error", "notification_reference_id": str(inbound_id)},
            )
        except Exception:
            pass
        record_audit_event(action="assistant.message", success=False, http_status=500,
                           entity_type="assistant_message", entity_id=str(inbound_id),
                           details={"channel": "ui", "store_id": store_id, "error": str(ex)})
        return jsonify({"error": answer}), 500


@assistant_bp.post("/task/<int:task_id>/confirm")
def confirm(task_id: int):
    data = request.get_json(silent=True) or {}
    store_id = int(data.get("store_id") or 0)
    if not can_access_store(store_id):
        return jsonify({"error": "Δεν έχετε πρόσβαση σε αυτό το κατάστημα"}), 403
    from app.repo_telegram_assistant import confirm_ui_task, record_ui_outbound_message
    task = confirm_ui_task(task_id=task_id, store_id=store_id, office_user=_user())
    if not task:
        return jsonify({"error": "Η εντολή δεν είναι διαθέσιμη για επιβεβαίωση"}), 409
    from app.assistant_execution_service import execute_confirmed_task, execution_answer
    result = execute_confirmed_task(task, source="assistant_ui")
    answer = execution_answer(task_id, result)
    record_ui_outbound_message(office_user=_user(), store_id=store_id, text=answer,
                               context={"notification_type": "assistant_confirmation", "notification_reference_id": str(task_id)})
    record_audit_event(action="assistant.execute", success=bool(result.get("success")), entity_type="assistant_task",
                       entity_id=str(task_id), details={"channel": "ui", "store_id": store_id, "result": result})
    return jsonify({"success": bool(result.get("success")), "answer": answer, "task": task, "execution": result})
