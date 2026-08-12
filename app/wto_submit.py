"""Κοινή υποβολή εγγράφων Οργάνωσης Χρόνου Εργασίας (WTODaily, WTODailyA, WTOOvA)."""

from __future__ import annotations

import json
from typing import Any

from flask import session

from app.ergani_client import ErganiClient
from app.http_helpers import json_or_text, normalize_multiline_text, response_body_text
from app.repo_card import insert_declaration, parse_ergani_submit_response


def clear_ergani_bearer_session() -> None:
    session.pop("ergani_bearer", None)
    session.pop("ergani_bearer_store_id", None)
    session.pop("ergani_bearer_env", None)


def ergani_authorization_denied(resp: Any, parsed: Any = None) -> bool:
    try:
        if int(getattr(resp, "status_code", 0) or 0) in (401, 403):
            return True
    except Exception:
        pass

    parts: list[str] = []
    if isinstance(parsed, dict):
        for key in ("message", "Message", "error", "Error", "detail", "Detail"):
            value = parsed.get(key)
            if value:
                parts.append(str(value))
    elif isinstance(parsed, str):
        parts.append(parsed)
    elif isinstance(parsed, list):
        for item in parsed:
            if isinstance(item, dict):
                for key in ("message", "Message", "error", "Error", "detail", "Detail"):
                    value = item.get(key)
                    if value:
                        parts.append(str(value))
            elif item:
                parts.append(str(item))

    body = response_body_text(resp)
    if body:
        parts.append(body)
    text = " ".join(parts).lower()
    return "authorization has been denied" in text


def submit_wto_with_auth_retry(
    ctx: dict[str, Any],
    client: ErganiClient,
    submission_code: str,
    payload: dict[str, Any],
    bearer: str,
    *,
    refresh_bearer,
) -> tuple[Any, Any, bool]:
    resp = client.document_submit(submission_code, payload, bearer)
    parsed = json_or_text(resp)
    if not ergani_authorization_denied(resp, parsed):
        return resp, parsed, False

    clear_ergani_bearer_session()
    refreshed = refresh_bearer(ctx)
    if not refreshed:
        return resp, parsed, False

    resp = client.document_submit(submission_code, payload, refreshed)
    parsed = json_or_text(resp)
    return resp, parsed, True


def persist_wto_submit(
    submission_code: str,
    employer_afm: str,
    http_status: int,
    success: bool,
    request_dict: dict[str, Any],
    response_body: str | None,
    protocol: str | None,
    submit_date_text: str | None,
    ergani_submission_id: str | None = None,
) -> int | None:
    from app.db import cursor

    req_str = json.dumps(request_dict, ensure_ascii=False)
    parsed_id, parsed_proto, parsed_date = parse_ergani_submit_response(response_body)
    with cursor() as cur:
        return insert_declaration(
            cur,
            submission_code,
            employer_afm,
            protocol or parsed_proto,
            submit_date_text or parsed_date,
            ergani_submission_id or parsed_id,
            http_status,
            success,
            req_str,
            response_body,
        )


def parse_submit_response(parsed: Any) -> tuple[str | None, str | None, str | None]:
    protocol = submit_date = ergani_id = None
    if isinstance(parsed, list) and parsed:
        first_item = parsed[0]
        if isinstance(first_item, dict):
            protocol = first_item.get("protocol")
            submit_date = first_item.get("submitDate")
            raw_id = first_item.get("id")
            ergani_id = str(raw_id).strip() if raw_id is not None else None
    return protocol, submit_date, ergani_id


def ergani_error_message(parsed: Any) -> str | None:
    if not isinstance(parsed, dict):
        return None
    raw = str(parsed.get("message") or parsed.get("Message") or "").strip()
    return normalize_multiline_text(raw) or None


def execute_wto_document_submit(
    ctx: dict[str, Any],
    *,
    submission_code: str,
    payload: dict[str, Any],
    refresh_bearer,
) -> tuple[Any | None, Any, bool, int | None]:
    bearer = refresh_bearer(ctx)
    if not bearer:
        return None, {"error": "Αποτυχία σύνδεσης Ergani API (web user)"}, False

    client = ErganiClient(ctx.get("api_base_url"))
    resp, parsed, auth_retry = submit_wto_with_auth_retry(
        ctx,
        client,
        submission_code,
        payload,
        bearer,
        refresh_bearer=refresh_bearer,
    )
    protocol, submit_date, ergani_id = parse_submit_response(parsed)
    declaration_id = persist_wto_submit(
        submission_code,
        str(ctx["employer_afm"]),
        resp.status_code,
        resp.ok,
        payload,
        response_body_text(resp),
        protocol,
        submit_date,
        ergani_id,
    )
    return resp, parsed, auth_retry, declaration_id
