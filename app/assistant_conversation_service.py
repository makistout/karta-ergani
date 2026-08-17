"""Channel-neutral AI assistant parsing and task creation."""

from __future__ import annotations

from typing import Any


def process_assistant_command(
    *, text: str, contexts: list[dict[str, Any]], inbound_id: int,
    recipient_id: int | None = None, store_id: int | None = None,
    reply_context: dict[str, Any] | None = None, confirmation_mode: str = "pin",
) -> dict[str, Any]:
    from app.repo_telegram_assistant import create_task, mark_inbound
    from app.telegram_assistant_service import parse_command, validate_and_describe

    parsed, employees, llm_metadata = parse_command(
        text=text, contexts=contexts, reply_context=dict(reply_context or {}),
    )
    status, validation, proposed = validate_and_describe(
        parsed, contexts=contexts, employees=employees,
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
    else:
        problems = "\n".join(f"• {item}" for item in validation.get("errors") or [])
        answer = f"Η εντολή #{task_id} χρειάζεται διευκρίνιση:\n{problems}\n\nΔεν έγινε καμία αποστολή στο ΕΡΓΑΝΗ."
    return {
        "task_id": task_id, "status": status, "task_status": task_status,
        "answer": answer, "parsed": parsed, "validation": validation,
        "proposed": proposed, "recipient_id": selected_recipient,
    }
