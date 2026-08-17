"""Execute a confirmed AI-assistant task through the existing Ergani flows."""

from __future__ import annotations

import json
from typing import Any

from app.repo_store import get_action_settings, get_store_config


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
    response = client.authenticate(username, password, usertype)
    data = json_or_text(response)
    token = str(data.get("accessToken") or "").strip() if response.ok and isinstance(data, dict) else ""
    if not token:
        raise RuntimeError(f"Αποτυχία σύνδεσης στο ΕΡΓΑΝΗ (HTTP {response.status_code})")
    return token, client


def _employees(store: dict[str, Any], afms: list[str]) -> list[dict[str, Any]]:
    from app.repo_entities import list_employees_for_employer

    wanted = set(afms)
    rows = list_employees_for_employer(
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
) -> list[dict[str, Any]]:
    store_id = int(parsed.get("store_id") or store.get("id") or 0)
    afms = [str(value or "").strip() for value in (parsed.get("employee_afms") or []) if str(value or "").strip()]
    if not afms and parsed.get("employee_afm"):
        afms = [str(parsed["employee_afm"]).strip()]
    employees = _employees(store, afms)
    intent = str(parsed.get("intent") or "")
    results: list[dict[str, Any]] = []
    for index, employee in enumerate(employees, start=1):
        name = f"{employee.get('eponymo') or ''} {employee.get('onoma') or ''}".strip()
        if intent.startswith("card_check_"):
            from app.routes_work_card import _submit_work_card
            event = "check_in" if "check_in" in intent else "check_out"
            event_time = None
            if intent.endswith("_retro"):
                event_time = str(parsed.get("time") or "")
            elif intent.endswith("_schedule"):
                event_time = str((parsed.get("resolved_schedule_times") or {}).get(str(employee.get("afm") or "")) or "")
            body = {
                "employee_afm": employee.get("afm"), "eponymo": employee.get("eponymo"),
                "onoma": employee.get("onoma"), "employee_name": name, "event": event,
                "reference_date": parsed.get("date"), "source": source,
                "batch_index": index, "batch_total": len(employees),
            }
            if event_time:
                body["event_at"] = f"{parsed.get('date')}T{event_time}:00"
            response, status = _submit_work_card(
                body=body, erg_s=str(store.get("employer_afm") or ""),
                aa_s=str(store.get("branch_aa") or "0"), bearer=bearer,
                api_base_url=client.base_url, store_id=store_id,
            )
            data = response.get_json() if hasattr(response, "get_json") else {}
            row = {"employee": name, "success": status == 200 and bool(data.get("success")),
                   "protocol": data.get("protocol"), "http_status": status, "error": data.get("error")}
        elif intent in {"schedule_change", "rest_day"}:
            from app.schedule_import_service import apply_import_row
            schedule_row = {
                "employee_afm": employee.get("afm"), "eponymo": employee.get("eponymo"),
                "onoma": employee.get("onoma"), "work_date": parsed.get("date"),
                "import_action": "rest" if intent == "rest_day" else "work",
                "proposed_snapshot": [] if intent == "rest_day" else [{
                    "hour_from": parsed.get("hour_from"), "hour_to": parsed.get("hour_to"),
                }], "comments": "Υποβολή από AI Agent",
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

    try:
        bearer, client = _authenticate(store)
        store["api_base_url"] = client.base_url
        results: list[dict[str, Any]] = []
        commands = parsed.get("commands") if isinstance(parsed.get("commands"), list) else [parsed]
        for command in commands:
            if isinstance(command, dict):
                results.extend(_execute_command(store, bearer, client, command, source=source))
        success = bool(results) and all(bool(row.get("success")) for row in results)
        result = {"success": success, "results": results}
    except Exception as exc:
        result = {"success": False, "results": [], "error": str(exc)}

    finish_task_execution(task_id, success=bool(result.get("success")), result=result)
    return result


def execution_answer(task_id: int, result: dict[str, Any]) -> str:
    lines = [f"Εντολή #{task_id}:"]
    for row in result.get("results") or []:
        if row.get("success"):
            protocol = str(row.get("protocol") or "—")
            lines.append(f"{row.get('employee') or 'Εργαζόμενος'} · Επιτυχία · Πρωτόκολλο: {protocol}")
        else:
            lines.append(f"{row.get('employee') or 'Εργαζόμενος'} · Αποτυχία · {row.get('error') or 'Άγνωστο σφάλμα'}")
    if not result.get("results"):
        lines.append(f"Αποτυχία · {result.get('error') or 'Άγνωστο σφάλμα'}")
    return "\n".join(lines)
