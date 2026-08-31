"""Ομαδική υποβολή απολογιστικού στο Ergani (ένα πρωτόκολλο ανά τύπο εγγράφου)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app.apologistic_submit import (
    load_apologistic_day_row,
    overtime_submit_group_from_row,
    parse_proposed_leave,
    schedule_body_from_apologistic_row,
    work_date_to_reference_iso,
)
from app.leave_payload import SUBMISSION_CODE_WTO_LEAVE, build_wto_leave_batch_payload
from app.repo_apologistic import record_ergani_submit, successful_overtime_minutes_for_year
from app.routes_wto_apologistic import execute_apologistic_wto_submit
from app.wto_daily_payload import SUBMISSION_CODE_WTO_DAILY_A, build_wto_daily_a_batch_payload
from app.wto_ov_payload import SUBMISSION_CODE_WTO_OV_A, build_wto_ov_a_batch_payload
from app.wto_submit import ergani_error_message, parse_submit_response
from app.work_card_payload import WorkCardPayloadError


def _item_key(item: dict[str, Any]) -> tuple[str, str, str, str]:
    return (
        str(item.get("kind") or "").strip(),
        str(item.get("employee_afm") or "").strip(),
        str(item.get("work_date") or "").strip(),
        str(item.get("segment_date") or "").strip(),
    )


def _schedule_needs_submit(row: dict[str, Any]) -> bool:
    ergani = row.get("ergani_submit") if isinstance(row.get("ergani_submit"), dict) else {}
    entry = ergani.get("schedule") if isinstance(ergani, dict) else None
    if not isinstance(entry, dict):
        return True
    protocol = str(entry.get("protocol") or "").strip()
    if not protocol:
        return True
    proposed = str(row.get("proposed") or "").strip()
    submitted = str(entry.get("proposed_at_submit") or "").strip()
    return bool(proposed and submitted and proposed != submitted)


def _overtime_needs_submit(row: dict[str, Any], segment_date: str) -> bool:
    ergani = row.get("ergani_submit") if isinstance(row.get("ergani_submit"), dict) else {}
    overtime = ergani.get("overtime") if isinstance(ergani, dict) else {}
    entry = overtime.get(segment_date) if isinstance(overtime, dict) else None
    if not isinstance(entry, dict):
        return True
    return not str(entry.get("protocol") or "").strip()


def _overtime_minutes_for_intervals(intervals: list[dict[str, Any]]) -> int:
    total = 0
    for interval in intervals:
        start = datetime.strptime(str(interval.get("hour_from") or ""), "%H:%M")
        end = datetime.strptime(str(interval.get("hour_to") or ""), "%H:%M")
        minutes = int((end - start).total_seconds() // 60)
        total += minutes + (1440 if minutes < 0 else 0)
    return total


def _check_annual_overtime_limits(
    *,
    store_id: int,
    overtime_entries: list[dict[str, Any]],
    confirm_annual_limit: bool,
) -> dict[str, Any] | None:
    per_employee: dict[tuple[str, int], int] = {}
    for entry in overtime_entries:
        afm = str(entry["employee_afm"])
        year = datetime.strptime(str(entry["reference_date"])[:10], "%Y-%m-%d").year
        minutes = _overtime_minutes_for_intervals(entry.get("intervals") or [])
        per_employee[(afm, year)] = per_employee.get((afm, year), 0) + minutes

    violations: list[dict[str, Any]] = []
    for (afm, year), new_minutes in per_employee.items():
        submitted = successful_overtime_minutes_for_year(store_id=store_id, employee_afm=afm, year=year)
        projected = submitted + new_minutes
        if projected > 150 * 60:
            violations.append({
                "employee_afm": afm,
                "year": year,
                "annual_submitted_minutes": submitted,
                "new_overtime_minutes": new_minutes,
                "projected_annual_minutes": projected,
            })
    if not violations or confirm_annual_limit:
        return None
    first = violations[0]
    year = first["year"]
    projected = first["projected_annual_minutes"]
    return {
        "error": (
            f"Με τη νέα υποβολή οι επιτυχώς υποβλημένες υπερωρίες του {year} "
            f"θα φτάσουν {projected // 60}:{projected % 60:02d}, πάνω από το όριο των 150 ωρών."
        ),
        "requires_confirmation": True,
        "violations": violations,
    }


def prepare_bulk_submit_groups(
    *,
    store_id: int,
    week_from,
    items: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    seen: set[tuple[str, str, str, str]] = set()
    schedule_targets: list[dict[str, Any]] = []
    leave_targets: list[dict[str, Any]] = []
    overtime_targets: list[dict[str, Any]] = []
    resolved: list[dict[str, Any]] = []

    for raw in items:
        if not isinstance(raw, dict):
            continue
        key = _item_key(raw)
        if key in seen:
            continue
        seen.add(key)

        kind = key[0]
        employee_afm = key[1]
        work_date_str = key[2]
        segment_date = key[3] or work_date_str
        if kind not in {"schedule", "overtime"}:
            raise WorkCardPayloadError(f"Άγνωστος τύπος υποβολής: {kind}")
        if len(employee_afm) != 9 or not employee_afm.isdigit():
            raise ValueError("Μη έγκυρο ΑΦΜ εργαζομένου")
        work_date = datetime.strptime(work_date_str, "%d/%m/%Y").date()
        item_week_from = raw.get("week_from") or week_from
        if isinstance(item_week_from, str):
            item_week = datetime.strptime(str(item_week_from)[:10], "%Y-%m-%d").date()
        else:
            item_week = week_from

        row = load_apologistic_day_row(
            store_id=store_id,
            week_from=item_week,
            employee_afm=employee_afm,
            work_date=work_date,
        )
        if str(row.get("status") or "").strip() != "change":
            continue

        if kind == "schedule":
            if not _schedule_needs_submit(row):
                continue
            leave_type = parse_proposed_leave(str(row.get("proposed") or ""))
            if leave_type:
                leave_targets.append({
                    "row": row,
                    "work_date": work_date,
                    "week_from": item_week,
                    "employee_afm": employee_afm,
                    "payload": {
                        "employee_afm": employee_afm,
                        "employee_last_name": str(row.get("eponymo") or ""),
                        "employee_first_name": str(row.get("onoma") or ""),
                        "reference_date": work_date_to_reference_iso(str(row.get("work_date") or "")),
                        "leave_type": leave_type,
                    },
                    "proposed_at_submit": str(row.get("proposed") or "").strip() or None,
                })
            else:
                schedule_body = schedule_body_from_apologistic_row(row)
                schedule_targets.append({
                    "row": row,
                    "work_date": work_date,
                    "week_from": item_week,
                    "employee_afm": employee_afm,
                    "payload": {
                        "employee_afm": employee_afm,
                        "employee_last_name": schedule_body["eponymo"],
                        "employee_first_name": schedule_body["onoma"],
                        "reference_date": schedule_body["reference_date"],
                        "schedule_type": schedule_body.get("schedule_type") or "ΕΡΓ",
                        "hour_from": schedule_body.get("hour_from"),
                        "hour_to": schedule_body.get("hour_to"),
                        "intervals": schedule_body.get("intervals"),
                    },
                    "proposed_at_submit": schedule_body.get("proposed"),
                })
            resolved.append({**raw, "work_date_obj": work_date})
            continue

        if not _overtime_needs_submit(row, segment_date):
            continue
        reference_date, day_segments = overtime_submit_group_from_row(
            row,
            segment_date_ergani=segment_date,
        )
        overtime_targets.append({
            "row": row,
            "work_date": work_date,
            "week_from": item_week,
            "employee_afm": employee_afm,
            "segment_date_ergani": segment_date,
            "reference_date": reference_date,
            "payload": {
                "employee_afm": employee_afm,
                "employee_last_name": str(row.get("eponymo") or ""),
                "employee_first_name": str(row.get("onoma") or ""),
                "reference_date": reference_date,
                "intervals": [{"hour_from": s["hour_from"], "hour_to": s["hour_to"]} for s in day_segments],
            },
        })
        resolved.append({**raw, "work_date_obj": work_date})

    return schedule_targets, leave_targets, overtime_targets, resolved


def execute_bulk_apologistic_submit(
    ctx: dict[str, Any],
    *,
    week_from,
    items: list[dict[str, Any]],
    confirm_annual_limit: bool = False,
    submitted_by: str | None = None,
    comments: str | None = None,
) -> dict[str, Any]:
    store_id = int(ctx["id"])
    schedule_targets, leave_targets, overtime_targets, _resolved = prepare_bulk_submit_groups(
        store_id=store_id,
        week_from=week_from,
        items=items,
    )
    if not schedule_targets and not leave_targets and not overtime_targets:
        raise WorkCardPayloadError("Δεν υπάρχουν εκκρεμείς υποβολές προς αποστολή")

    limit_error = _check_annual_overtime_limits(
        store_id=store_id,
        overtime_entries=[entry["payload"] for entry in overtime_targets],
        confirm_annual_limit=confirm_annual_limit,
    )
    if limit_error:
        return {"success": False, **limit_error}

    branch_aa = str(ctx.get("branch_aa") or "0")
    results: list[dict[str, Any]] = []
    protocols: dict[str, str | None] = {
        "schedule": None,
        "leave": None,
        "overtime": None,
    }

    def _submit_group(
        *,
        submission_code: str,
        payload: dict[str, Any],
        audit_action: str,
        targets: list[dict[str, Any]],
        persist_overtime: bool,
        protocol_key: str,
    ) -> None:
        if not targets:
            return
        resp, parsed, _auth_retry, declaration_id = execute_apologistic_wto_submit(
            ctx,
            submission_code=submission_code,
            payload=payload,
            audit_action=audit_action,
            employee_afm=str(targets[0]["employee_afm"]),
            reference_date=str(targets[0]["payload"]["reference_date"]),
            audit_details={
                "source": "apologistic_bulk",
                "batch_count": len(targets),
                "week_from": week_from.isoformat(),
            },
        )
        if resp is None:
            raise PermissionError(str(parsed))
        if not resp.ok:
            raise WorkCardPayloadError(ergani_error_message(parsed) or "Αποτυχία ομαδικής υποβολής Ergani")

        protocol, submit_date, ergani_id = parse_submit_response(parsed)
        protocols[protocol_key] = protocol

        for target in targets:
            segment_ref = None
            if persist_overtime:
                try:
                    segment_ref = datetime.strptime(str(target["reference_date"])[:10], "%Y-%m-%d").date()
                except ValueError:
                    segment_ref = target["work_date"]
            fragment = record_ergani_submit(
                store_id=store_id,
                week_from=target.get("week_from") or week_from,
                employee_afm=str(target["employee_afm"]),
                work_date=target["work_date"],
                submission_code=submission_code,
                declaration_id=declaration_id,
                success=True,
                protocol=protocol,
                ergani_submission_id=ergani_id,
                submit_date_text=submit_date,
                proposed_at_submit=target.get("proposed_at_submit"),
                segment_reference_date=segment_ref if persist_overtime else None,
                submitted_by=submitted_by,
            )
            results.append({
                "employee_afm": target["employee_afm"],
                "work_date": target["row"].get("work_date"),
                "submission_code": submission_code,
                "protocol": protocol,
                "ergani_submit": fragment,
                "segment_date": target.get("segment_date_ergani"),
            })

    if schedule_targets:
        _submit_group(
            submission_code=SUBMISSION_CODE_WTO_DAILY_A,
            payload=build_wto_daily_a_batch_payload(
                branch_aa=branch_aa,
                employees=[entry["payload"] for entry in schedule_targets],
                comments=comments,
            ),
            audit_action="apologistic.submit_schedule_batch",
            targets=schedule_targets,
            persist_overtime=False,
            protocol_key="schedule",
        )

    if leave_targets:
        _submit_group(
            submission_code=SUBMISSION_CODE_WTO_LEAVE,
            payload=build_wto_leave_batch_payload(
                branch_aa=branch_aa,
                employees=[entry["payload"] for entry in leave_targets],
                comments=comments,
            ),
            audit_action="apologistic.submit_leave_batch",
            targets=leave_targets,
            persist_overtime=False,
            protocol_key="leave",
        )

    if overtime_targets:
        _submit_group(
            submission_code=SUBMISSION_CODE_WTO_OV_A,
            payload=build_wto_ov_a_batch_payload(
                branch_aa=branch_aa,
                employees=[entry["payload"] for entry in overtime_targets],
                comments=comments,
            ),
            audit_action="apologistic.submit_overtime_batch",
            targets=overtime_targets,
            persist_overtime=True,
            protocol_key="overtime",
        )

    submitted_codes = sum(1 for value in protocols.values() if value)
    return {
        "success": True,
        "protocols": protocols,
        "submission_count": submitted_codes,
        "row_count": len(results),
        "results": results,
    }


__all__ = ["execute_bulk_apologistic_submit", "prepare_bulk_submit_groups"]
