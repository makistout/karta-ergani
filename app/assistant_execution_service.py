"""Execute a confirmed AI-assistant task through the existing Ergani flows."""

from __future__ import annotations

import json
import hashlib
import threading
import time
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from app.repo_store import get_action_settings, get_store_config


_AUTH_CACHE_LOCK = threading.RLock()
_AUTH_CACHE: dict[tuple[Any, ...], tuple[str, float]] = {}
_AUTH_CACHE_DEFAULT_TTL_SEC = 300.0
_AUTH_CACHE_EXPIRY_MARGIN_SEC = 30.0
_ATHENS = ZoneInfo("Europe/Athens")


def _payload(task: dict[str, Any]) -> dict[str, Any]:
    value = task.get("payload")
    if isinstance(value, dict):
        return value
    try:
        parsed = json.loads(str(task.get("payload_json") or "{}"))
    except (TypeError, ValueError):
        parsed = {}
    return parsed if isinstance(parsed, dict) else {}


def _authenticate(store: dict[str, Any]) -> tuple[str, Any]:
    from app.ergani_env import api_login_credentials, client_for_store
    from app.http_helpers import json_or_text

    client = client_for_store(store)
    username, password, usertype = api_login_credentials(store)
    password_fingerprint = hashlib.sha256(str(password).encode("utf-8")).hexdigest()
    cache_key = (
        int(store.get("id") or 0),
        str(store.get("ergani_env") or ""),
        str(client.base_url),
        str(username),
        str(usertype),
        password_fingerprint,
    )
    now_mono = time.monotonic()
    with _AUTH_CACHE_LOCK:
        cached = _AUTH_CACHE.get(cache_key)
        if cached and cached[1] > now_mono:
            return cached[0], client
        if cached:
            _AUTH_CACHE.pop(cache_key, None)

    response = client.authenticate(username, password, usertype)
    data = json_or_text(response)
    token = str(data.get("accessToken") or "").strip() if response.ok and isinstance(data, dict) else ""
    if not token:
        raise RuntimeError(f"Αποτυχία σύνδεσης στο ΕΡΓΑΝΗ (HTTP {response.status_code})")
    try:
        reported_ttl = float(data.get("accessTokenExpired") or _AUTH_CACHE_DEFAULT_TTL_SEC)
    except (TypeError, ValueError):
        reported_ttl = _AUTH_CACHE_DEFAULT_TTL_SEC
    cache_ttl = max(0.0, reported_ttl - _AUTH_CACHE_EXPIRY_MARGIN_SEC)
    if cache_ttl > 0:
        with _AUTH_CACHE_LOCK:
            _AUTH_CACHE[cache_key] = (token, now_mono + cache_ttl)
    return token, client


def _clear_auth_cache() -> None:
    """Clear process-local Ergani tokens (tests/reconfiguration)."""
    with _AUTH_CACHE_LOCK:
        _AUTH_CACHE.clear()


def _employees(store: dict[str, Any], afms: list[str]) -> list[dict[str, Any]]:
    from app.repo_entities import list_active_employees_for_store

    wanted = set(afms)
    rows = list_active_employees_for_store(
        str(store.get("employer_afm") or ""), str(store.get("branch_aa") or "0"), limit=5000,
    )
    by_afm = {str(row.get("afm") or "").strip(): row for row in rows}
    missing = [afm for afm in afms if afm not in by_afm]
    if missing:
        raise RuntimeError("Δεν βρέθηκαν όλοι οι εργαζόμενοι στη βάση")
    return [by_afm[afm] for afm in afms]


def _leave_code(value: str) -> str:
    from app.leave_types import LEAVE_TYPES

    raw = str(value or "").strip()
    folded = raw.casefold()
    for item in LEAVE_TYPES:
        if raw.upper() == item["code"] or folded in item["label"].casefold() or item["label"].casefold() in folded:
            return item["code"]
    raise RuntimeError(f"Μη αναγνωρισμένος τύπος άδειας: {raw or '—'}")


def _submit_leave(store: dict[str, Any], bearer: str, client: Any, employee: dict[str, Any], parsed: dict[str, Any]) -> dict[str, Any]:
    from app.http_helpers import json_or_text, persist_safe, response_body_text
    from app.leave_payload import SUBMISSION_CODE_WTO_LEAVE, build_wto_leave_payload
    from app.routes_leave import _persist_leave_submit

    payload = build_wto_leave_payload(
        branch_aa=str(store.get("branch_aa") or "0"),
        employee_afm=str(employee.get("afm") or ""),
        employee_last_name=str(employee.get("eponymo") or ""),
        employee_first_name=str(employee.get("onoma") or ""),
        reference_date=str(parsed.get("date") or ""),
        leave_type=_leave_code(str(parsed.get("leave_type") or "")),
        comments="Υποβολή από AI Agent",
        hour_from=parsed.get("hour_from"), hour_to=parsed.get("hour_to"),
    )
    response = client.document_submit(SUBMISSION_CODE_WTO_LEAVE, payload, bearer)
    data = json_or_text(response)
    item = data[0] if response.ok and isinstance(data, list) and data and isinstance(data[0], dict) else {}
    protocol = item.get("protocol")
    persist_safe(
        _persist_leave_submit, str(store.get("employer_afm") or ""), response.status_code,
        response.ok, payload, response_body_text(response), protocol, item.get("submitDate"),
        str(item.get("id") or "") or None,
    )
    return {"success": response.ok, "protocol": protocol, "http_status": response.status_code,
            "error": None if response.ok else str(data)[:500]}


def _execute_command(
    store: dict[str, Any], bearer: str, client: Any, parsed: dict[str, Any], *, source: str,
    punch_index_offset: int = 0, punch_total: int = 1,
    stagger_offsets: list[int] | None = None,
    queue_wall_start: float | None = None,
    queue_base_now: datetime | None = None,
) -> list[dict[str, Any]]:
    store_id = int(parsed.get("store_id") or store.get("id") or 0)
    afms = [str(value or "").strip() for value in (parsed.get("employee_afms") or []) if str(value or "").strip()]
    if not afms and parsed.get("employee_afm"):
        afms = [str(parsed["employee_afm"]).strip()]
    employees = _employees(store, afms)
    intent = str(parsed.get("intent") or "")
    results: list[dict[str, Any]] = []
    offsets = list(stagger_offsets or [])
    wall_start = float(queue_wall_start) if queue_wall_start is not None else time.monotonic()
    base_now = queue_base_now or datetime.now(_ATHENS)

    if intent == "sync_employees":
        from app.ergani_env import store_api_context
        from app.portal_employment_contract_sync import sync_employment_contracts_from_portal

        store_for_ctx = dict(store)
        store_for_ctx.setdefault("name", store.get("name") or f"store-{store_id}")
        ctx = store_api_context(store_for_ctx)
        sync_result = sync_employment_contracts_from_portal(ctx)
        ok = bool(sync_result.get("success"))
        detail = str(sync_result.get("detail") or ("OK" if ok else "Αποτυχία"))
        count = sync_result.get("count")
        qr_synced = sync_result.get("qr_synced")
        linked = sync_result.get("linked_employees")
        parts = [detail]
        if count is not None:
            parts.append(f"συμβάσεις={count}")
        if qr_synced is not None:
            parts.append(f"QR={qr_synced}")
        if linked is not None:
            parts.append(f"συνδέσεις={linked}")
        summary = " · ".join(str(p) for p in parts if p is not None and str(p).strip())
        return [{
            "employee": "Προσωπικό",
            "success": ok,
            "protocol": None,
            "detail": summary,
            "count": count,
            "qr_synced": qr_synced,
            "linked_employees": linked,
            "error": None if ok else summary,
        }]

    for index, employee in enumerate(employees, start=1):
        name = f"{employee.get('eponymo') or ''} {employee.get('onoma') or ''}".strip()
        global_batch_index = punch_index_offset + index
        zero_based = global_batch_index - 1
        offset_min = 0
        if punch_total > 1 and zero_based >= 0:
            if zero_based < len(offsets):
                offset_min = int(offsets[zero_based] or 0)
            else:
                from app.punch_batch_stagger import cumulative_stagger_minutes

                offset_min = cumulative_stagger_minutes(zero_based)

        if (
            intent.endswith("_now")
            and punch_total > 1
            and offset_min > 0
        ):
            # Ουρά μόνο για ζωντανά «τώρα»: περίμενε μέχρι το λεπτό offset από την έναρξη.
            due = wall_start + (offset_min * 60.0)
            delay = due - time.monotonic()
            if delay > 0:
                time.sleep(delay)

        if intent.startswith("card_check_"):
            from app.routes_work_card import _submit_work_card
            from app.work_card_guards import new_card_punch_blocked_reason

            event = "check_in" if "check_in" in intent else "check_out"
            event_time = None
            if intent.endswith("_retro"):
                event_time = str(parsed.get("time") or "")
            elif intent.endswith("_schedule"):
                event_time = str((parsed.get("resolved_schedule_times") or {}).get(str(employee.get("afm") or "")) or "")

            ref_date = str(parsed.get("date") or base_now.date().isoformat())
            if event_time:
                try:
                    hh, mm = [int(part) for part in str(event_time).strip()[:5].split(":", 1)]
                    event_dt = datetime(
                        int(ref_date[0:4]), int(ref_date[5:7]), int(ref_date[8:10]),
                        hh, mm, 0, tzinfo=_ATHENS,
                    ) + timedelta(minutes=offset_min)
                except (TypeError, ValueError, IndexError):
                    event_dt = base_now + timedelta(minutes=offset_min)
            else:
                # «τώρα»: ίδια βάση για όλη την παρτίδα + stagger 1–2′.
                event_dt = base_now + timedelta(minutes=offset_min)
            event_at = event_dt.strftime("%Y-%m-%dT%H:%M:%S")

            blocked = new_card_punch_blocked_reason(
                intent=intent,
                employer_afm=str(store.get("employer_afm") or ""),
                branch_aa=str(store.get("branch_aa") or "0"),
                employee_afm=str(employee.get("afm") or ""),
                reference_date_iso=ref_date,
                event_at=event_at,
            )
            if blocked:
                results.append({
                    "employee": name,
                    "success": False,
                    "protocol": None,
                    "error": blocked,
                })
                continue
            body = {
                "employee_afm": employee.get("afm"), "eponymo": employee.get("eponymo"),
                "onoma": employee.get("onoma"), "employee_name": name, "event": event,
                "reference_date": ref_date, "source": source,
                # Ήδη εφαρμόσαμε stagger + ουρά· μην διπλο-μετατοπίσει το routes layer.
                "batch_index": 1,
                "batch_total": 1,
                "event_at": event_at,
            }
            response, status = _submit_work_card(
                body=body, erg_s=str(store.get("employer_afm") or ""),
                aa_s=str(store.get("branch_aa") or "0"), bearer=bearer,
                api_base_url=client.base_url, store_id=store_id,
            )
            data = response.get_json() if hasattr(response, "get_json") else {}
            row = {
                "employee": name,
                "success": status == 200 and bool(data.get("success")),
                "protocol": data.get("protocol"),
                "http_status": status,
                "error": data.get("error"),
                "event_at": event_at,
                "queue_offset_minutes": offset_min,
            }
        elif intent in {"schedule_change", "rest_day"}:
            from app.schedule_import_service import apply_import_row
            intervals = parsed.get("intervals") if isinstance(parsed.get("intervals"), list) else None
            if intent == "rest_day":
                proposed_snapshot: list[dict[str, Any]] = []
            elif intervals:
                proposed_snapshot = [
                    {
                        "hour_from": str(item.get("hour_from") or "").strip(),
                        "hour_to": str(item.get("hour_to") or "").strip(),
                    }
                    for item in intervals
                    if isinstance(item, dict)
                    and str(item.get("hour_from") or "").strip()
                    and str(item.get("hour_to") or "").strip()
                ]
            else:
                proposed_snapshot = [{
                    "hour_from": parsed.get("hour_from"), "hour_to": parsed.get("hour_to"),
                }]
            schedule_row = {
                "employee_afm": employee.get("afm"), "eponymo": employee.get("eponymo"),
                "onoma": employee.get("onoma"), "work_date": parsed.get("date"),
                "import_action": "rest" if intent == "rest_day" else "work",
                "proposed_snapshot": proposed_snapshot,
                "comments": "Υποβολή από AI Agent",
            }
            data = apply_import_row(store, schedule_row, bearer, batch_meta={"source": source})
            row = {"employee": name, "success": bool(data.get("success")),
                   "protocol": data.get("protocol"), "http_status": data.get("http_status"), "error": data.get("error")}
        elif intent == "leave":
            data = _submit_leave(store, bearer, client, employee, parsed)
            row = {"employee": name, **data}
        else:
            row = {"employee": name, "success": False, "protocol": None,
                   "error": f"Μη υποστηριζόμενη εκτέλεση: {intent}"}
        results.append(row)
    return results


def execute_confirmed_task(task: dict[str, Any], *, source: str) -> dict[str, Any]:
    from app.repo_telegram_assistant import finish_task_execution

    task_id = int(task["id"])
    parsed = _payload(task)
    store_id = int(task.get("store_id") or parsed.get("store_id") or 0)
    store = get_store_config(store_id)
    if not store:
        result = {"success": False, "results": [], "error": "Δεν βρέθηκε κατάστημα"}
        finish_task_execution(task_id, success=False, result=result)
        return result
    if not bool(get_action_settings(store_id).get("ai_agent_enabled")):
        result = {"success": False, "results": [], "error": "Ο AI Agent δεν είναι ενεργοποιημένος για το κατάστημα"}
        finish_task_execution(task_id, success=False, result=result)
        return result

    execution_started = time.monotonic()
    try:
        auth_started = time.monotonic()
        bearer, client = _authenticate(store)
        auth_ms = int((time.monotonic() - auth_started) * 1000)
        store["api_base_url"] = client.base_url
        results: list[dict[str, Any]] = []
        commands = parsed.get("commands") if isinstance(parsed.get("commands"), list) else [parsed]
        from app.punch_batch_stagger import count_card_punches_in_commands, precompute_batch_offsets

        normalized_commands = [command for command in commands if isinstance(command, dict)]
        punch_total = count_card_punches_in_commands(normalized_commands) or 1
        stagger_offsets = precompute_batch_offsets(punch_total) if punch_total > 1 else [0]
        queue_wall_start = time.monotonic()
        queue_base_now = datetime.now(_ATHENS)
        punch_offset = 0
        commands_started = time.monotonic()
        for command in normalized_commands:
            results.extend(
                _execute_command(
                    store, bearer, client, command, source=source,
                    punch_index_offset=punch_offset, punch_total=punch_total,
                    stagger_offsets=stagger_offsets,
                    queue_wall_start=queue_wall_start,
                    queue_base_now=queue_base_now,
                )
            )
            intent = str(command.get("intent") or "")
            if intent.startswith("card_check_"):
                afms = command.get("employee_afms")
                if not isinstance(afms, list):
                    afms = [command.get("employee_afm")] if command.get("employee_afm") else []
                punch_offset += len([str(a or "").strip() for a in afms if str(a or "").strip()])
        success = bool(results) and all(bool(row.get("success")) for row in results)
        result = {
            "success": success,
            "results": results,
            "timings_ms": {
                "authentication": auth_ms,
                "commands": int((time.monotonic() - commands_started) * 1000),
                "total": int((time.monotonic() - execution_started) * 1000),
            },
        }
    except Exception as exc:
        result = {
            "success": False,
            "results": [],
            "error": str(exc),
            "timings_ms": {"total": int((time.monotonic() - execution_started) * 1000)},
        }

    finish_task_execution(task_id, success=bool(result.get("success")), result=result)
    return result


def execution_answer(task_id: int, result: dict[str, Any]) -> str:
    lines = [f"Εντολή #{task_id}:"]
    for row in result.get("results") or []:
        if row.get("success"):
            protocol = str(row.get("protocol") or "").strip()
            detail = str(row.get("detail") or "").strip()
            if protocol:
                lines.append(f"{row.get('employee') or 'Εργαζόμενος'} · Επιτυχία · Πρωτόκολλο: {protocol}")
            elif detail:
                lines.append(f"{row.get('employee') or 'Εργαζόμενος'} · Επιτυχία · {detail}")
            else:
                lines.append(f"{row.get('employee') or 'Εργαζόμενος'} · Επιτυχία · Πρωτόκολλο: —")
        else:
            lines.append(f"{row.get('employee') or 'Εργαζόμενος'} · Αποτυχία · {row.get('error') or 'Άγνωστο σφάλμα'}")
    if not result.get("results"):
        lines.append(f"Αποτυχία · {result.get('error') or 'Άγνωστο σφάλμα'}")
    return "\n".join(lines)
