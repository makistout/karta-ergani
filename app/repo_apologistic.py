"""Persisted, editable weekly retrospective results."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import date, datetime
from typing import Any

from app.db import cursor
from app.apologistic_submit import parse_wto_request_meta
from app.row_util import row_to_dict, rows_to_dicts
from app.wto_daily_payload import SUBMISSION_CODE_WTO_DAILY_A
from app.wto_ov_payload import SUBMISSION_CODE_WTO_OV_A

_SUBMIT_TABLE = "karta_apologistic_submit"
_PROPOSED_TIME_SLOT = re.compile(
    r"^((?:[01]\d|2[0-3]):[0-5]\d)–((?:[01]\d|2[0-3]):[0-5]\d)$"
)
_PROPOSED_TELEWORK = re.compile(
    r"^ΤΗΛΕΡΓΑΣΙΑ\s+((?:[01]\d|2[0-3]):[0-5]\d)–((?:[01]\d|2[0-3]):[0-5]\d)$",
    re.IGNORECASE,
)


def normalize_proposed_value(proposed: str) -> str:
    """Κανονικοποιεί πρόταση σε αποθηκεύσιμη μορφή (ωράριο ή ειδική κατάσταση)."""
    value = str(proposed or "").strip()
    upper = value.upper()
    if not value:
        raise ValueError("Η πρόταση είναι κενή")
    if upper in {"ΑΝΑΠΑΥΣΗ/ΡΕΠΟ", "ΡΕΠΟ", "ΑΝΑΠΑΥΣΗ", "ΑΝ"}:
        return "ΑΝΑΠΑΥΣΗ/ΡΕΠΟ"
    if upper in {"ΜΗ ΕΡΓΑΣΙΑ", "ΜΕ"} or upper.startswith("ΜΗ ΕΡΓΑΣΙΑ"):
        return "ΜΗ ΕΡΓΑΣΙΑ"
    tele = _PROPOSED_TELEWORK.fullmatch(value)
    if tele:
        return f"ΤΗΛΕΡΓΑΣΙΑ {tele.group(1)}–{tele.group(2)}"
    if upper.startswith("ΤΗΛΕΡΓΑΣ") or upper.startswith("ΤΗΛ "):
        raise ValueError("Η τηλεργασία απαιτεί ωράριο σε μορφή ΤΗΛΕΡΓΑΣΙΑ ΩΩ:ΛΛ–ΩΩ:ΛΛ")
    slots = [part.strip() for part in value.split(" · ") if part.strip()]
    if slots:
        normalized_slots: list[str] = []
        for slot in slots:
            match = _PROPOSED_TIME_SLOT.fullmatch(slot)
            if not match:
                break
            normalized_slots.append(f"{match.group(1)}–{match.group(2)}")
        if len(normalized_slots) == len(slots) and 0 < len(normalized_slots) <= 2:
            return " · ".join(normalized_slots)
    raise ValueError(
        "Η πρόταση πρέπει να είναι ΩΩ:ΛΛ–ΩΩ:ΛΛ (ή σπαστό ΩΩ:ΛΛ–ΩΩ:ΛΛ · ΩΩ:ΛΛ–ΩΩ:ΛΛ), "
        "ΑΝΑΠΑΥΣΗ/ΡΕΠΟ, ΜΗ ΕΡΓΑΣΙΑ ή ΤΗΛΕΡΓΑΣΙΑ ΩΩ:ΛΛ–ΩΩ:ΛΛ"
    )


def tables_available() -> bool:
    try:
        with cursor(commit=False) as cur:
            cur.execute("SELECT OBJECT_ID(N'dbo.karta_apologistic_run', N'U'), OBJECT_ID(N'dbo.karta_apologistic_day', N'U')")
            row = cur.fetchone()
            return bool(row and row[0] and row[1])
    except Exception:
        return False


def get_run(store_id: int, week_from: date) -> dict[str, Any] | None:
    with cursor(commit=False) as cur:
        cur.execute("""
            SELECT id, store_id, employer_afm, branch_aa, week_from, week_to, status,
                   calculation_version, generated_report_json, effective_report_json,
                   error_summary,
                   CAST(started_at AS datetime2) AS started_at,
                   CAST(completed_at AS datetime2) AS completed_at,
                   CAST(created_at AS datetime2) AS created_at,
                   CAST(updated_at AS datetime2) AS updated_at
            FROM dbo.karta_apologistic_run WHERE store_id = ? AND week_from = ?
        """, (int(store_id), week_from))
        row = cur.fetchone()
        return row_to_dict(cur, row) if row else None


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), default=str)


def _merge(base: dict[str, Any], override: dict[str, Any] | None) -> dict[str, Any]:
    result = dict(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = _merge(result[key], value)
        else:
            result[key] = value
    return result


def save_report(*, store: dict[str, Any], week_from: date, week_to: date,
                report: dict[str, Any], calculation_version: str) -> dict[str, Any]:
    store_id = int(store["id"])
    with cursor(commit=True) as cur:
        # Connections are pooled, therefore SQL Server local temp tables may
        # survive until the same connection is checked out again.  Always
        # clean stale staging tables before starting a new store/week save.
        cur.execute("DROP TABLE IF EXISTS #apologistic_day_stage; DROP TABLE IF EXISTS #apologistic_rest_stage;")
        cur.execute("""
            SELECT id, status FROM dbo.karta_apologistic_run WITH (UPDLOCK, HOLDLOCK)
            WHERE store_id = ? AND week_from = ?
        """, (store_id, week_from))
        existing = cur.fetchone()
        if existing and str(existing[1]) in ("approved", "locked"):
            return {"run_id": int(existing[0]), "skipped": True, "reason": f"status={existing[1]}"}
        if existing:
            run_id = int(existing[0])
            cur.execute("""
                UPDATE dbo.karta_apologistic_run SET status=N'running', calculation_version=?,
                    employer_afm=?, branch_aa=?, week_to=?, error_summary=NULL,
                    started_at=SYSDATETIMEOFFSET(), updated_at=SYSDATETIMEOFFSET()
                WHERE id=?
            """, (calculation_version, store["employer_afm"], store["branch_aa"], week_to, run_id))
        else:
            cur.execute("""
                INSERT dbo.karta_apologistic_run
                    (store_id, employer_afm, branch_aa, week_from, week_to, status, calculation_version, started_at)
                OUTPUT INSERTED.id VALUES (?, ?, ?, ?, ?, N'running', ?, SYSDATETIMEOFFSET())
            """, (store_id, store["employer_afm"], store["branch_aa"], week_from, week_to, calculation_version))
            run_id = int(cur.fetchone()[0])

        cur.execute("SELECT employee_afm, work_date, override_json, review_status FROM dbo.karta_apologistic_day WHERE run_id=?", (run_id,))
        saved = {(str(r[0]), r[1]): (r[2], str(r[3])) for r in cur.fetchall()}
        effective_days: list[dict[str, Any]] = []
        day_stage: list[tuple[Any, ...]] = []
        for day in report.get("days") or []:
            work_date = datetime.strptime(str(day["work_date"]), "%d/%m/%Y").date()
            afm = str(day.get("employee_afm") or "")
            key = (afm, work_date)
            override_raw, review_status = saved.get(key, (None, "draft"))
            try:
                override = json.loads(override_raw) if override_raw else None
            except (TypeError, json.JSONDecodeError):
                override = None
            effective = _merge(day, override)
            effective_days.append(effective)
            day_stage.append((afm, work_date, _json(day), _json(effective)))

        cur.execute("""
            CREATE TABLE #apologistic_day_stage (
                employee_afm NVARCHAR(9) NOT NULL,
                work_date DATE NOT NULL,
                generated_json NVARCHAR(MAX) NOT NULL,
                effective_json NVARCHAR(MAX) NOT NULL,
                PRIMARY KEY (employee_afm, work_date)
            )
        """)
        if day_stage:
            day_payload = [{
                "employee_afm": row[0], "work_date": row[1].isoformat(),
                "generated_json": row[2], "effective_json": row[3],
            } for row in day_stage]
            cur.execute("""
                INSERT #apologistic_day_stage(employee_afm, work_date, generated_json, effective_json)
                SELECT employee_afm, work_date, generated_json, effective_json
                FROM OPENJSON(?) WITH (
                    employee_afm NVARCHAR(9) '$.employee_afm', work_date DATE '$.work_date',
                    generated_json NVARCHAR(MAX) '$.generated_json', effective_json NVARCHAR(MAX) '$.effective_json'
                )
            """, (_json(day_payload),))
        cur.execute("""
            MERGE dbo.karta_apologistic_day AS target
            USING #apologistic_day_stage AS source
            ON target.run_id=? AND target.employee_afm=source.employee_afm AND target.work_date=source.work_date
            WHEN MATCHED THEN UPDATE SET generated_json=source.generated_json,
                effective_json=source.effective_json, generated_at=SYSDATETIMEOFFSET(), updated_at=SYSDATETIMEOFFSET()
            WHEN NOT MATCHED THEN INSERT (run_id, store_id, employee_afm, work_date, generated_json, effective_json)
                VALUES (?, ?, source.employee_afm, source.work_date, source.generated_json, source.effective_json);
        """, (run_id, run_id, store_id))
        cur.execute("""
            DELETE target FROM dbo.karta_apologistic_day target
            WHERE target.run_id=? AND target.override_json IS NULL
              AND target.review_status NOT IN (N'approved', N'locked')
              AND NOT EXISTS (
                  SELECT 1 FROM #apologistic_day_stage source
                  WHERE source.employee_afm=target.employee_afm AND source.work_date=target.work_date
              )
        """, (run_id,))

        obligation_stage: list[tuple[Any, ...]] = []
        for day in report.get("days") or []:
            if not day.get("compensatory_rest_due"):
                continue
            source_date = datetime.strptime(str(day["work_date"]), "%d/%m/%Y").date()
            target_from = datetime.strptime(str(day["compensatory_rest_target_week"]), "%Y-%m-%d").date()
            afm = str(day.get("employee_afm") or "")
            obligation_stage.append((afm, source_date, int(day.get("effective_actual_minutes") or 0),
                                     int(day.get("weekly_punch_days") or 0), target_from,
                                     target_from.fromordinal(target_from.toordinal() + 6)))
        cur.execute("""
            CREATE TABLE #apologistic_rest_stage (
                employee_afm NVARCHAR(9) NOT NULL, source_work_date DATE NOT NULL,
                source_actual_minutes INT NOT NULL, source_punch_days INT NOT NULL,
                target_week_from DATE NOT NULL, target_week_to DATE NOT NULL,
                PRIMARY KEY(employee_afm, source_work_date)
            )
        """)
        if obligation_stage:
            obligation_payload = [{
                "employee_afm": row[0], "source_work_date": row[1].isoformat(),
                "source_actual_minutes": row[2], "source_punch_days": row[3],
                "target_week_from": row[4].isoformat(), "target_week_to": row[5].isoformat(),
            } for row in obligation_stage]
            cur.execute("""
                INSERT #apologistic_rest_stage
                    (employee_afm, source_work_date, source_actual_minutes, source_punch_days, target_week_from, target_week_to)
                SELECT employee_afm, source_work_date, source_actual_minutes, source_punch_days, target_week_from, target_week_to
                FROM OPENJSON(?) WITH (
                    employee_afm NVARCHAR(9) '$.employee_afm', source_work_date DATE '$.source_work_date',
                    source_actual_minutes INT '$.source_actual_minutes', source_punch_days INT '$.source_punch_days',
                    target_week_from DATE '$.target_week_from', target_week_to DATE '$.target_week_to'
                )
            """, (_json(obligation_payload),))
        cur.execute("""
            MERGE dbo.karta_apologistic_rest_obligation AS target
            USING #apologistic_rest_stage AS source
            ON target.store_id=? AND target.employee_afm=source.employee_afm
               AND target.source_work_date=source.source_work_date
            WHEN MATCHED AND target.status=N'pending' THEN UPDATE SET source_run_id=?,
                source_actual_minutes=source.source_actual_minutes, source_punch_days=source.source_punch_days,
                target_week_from=source.target_week_from, target_week_to=source.target_week_to,
                updated_at=SYSDATETIMEOFFSET()
            WHEN NOT MATCHED THEN INSERT
                (store_id, employee_afm, source_run_id, source_work_date, source_actual_minutes,
                 source_punch_days, target_week_from, target_week_to)
                VALUES (?, source.employee_afm, ?, source.source_work_date, source.source_actual_minutes,
                        source.source_punch_days, source.target_week_from, source.target_week_to);
        """, (store_id, run_id, store_id, run_id))
        cur.execute("""
            UPDATE target SET status=N'cancelled',
                resolution_note=N'Δεν προκύπτει πλέον μετά τον επανυπολογισμό',
                resolved_at=SYSDATETIMEOFFSET(), updated_at=SYSDATETIMEOFFSET()
            FROM dbo.karta_apologistic_rest_obligation target
            WHERE target.store_id=? AND target.source_work_date BETWEEN ? AND ?
              AND target.status=N'pending' AND NOT EXISTS (
                  SELECT 1 FROM #apologistic_rest_stage source
                  WHERE source.employee_afm=target.employee_afm
                    AND source.source_work_date=target.source_work_date
              )
        """, (store_id, week_from, week_to))

        effective_report = dict(report)
        effective_report["days"] = effective_days
        # Until field-level editing is exposed, summaries are identical; day overrides remain authoritative.
        cur.execute("""
            UPDATE dbo.karta_apologistic_run SET status=N'draft', generated_report_json=?,
                effective_report_json=?, completed_at=SYSDATETIMEOFFSET(), updated_at=SYSDATETIMEOFFSET()
            WHERE id=?
        """, (_json(report), _json(effective_report), run_id))
        cur.execute("DROP TABLE IF EXISTS #apologistic_day_stage; DROP TABLE IF EXISTS #apologistic_rest_stage;")
        return {"run_id": run_id, "skipped": False, "days": len(effective_days)}


def mark_failed(*, store: dict[str, Any], week_from: date, week_to: date,
                calculation_version: str, error: str) -> None:
    with cursor(commit=True) as cur:
        cur.execute("""
            MERGE dbo.karta_apologistic_run AS target
            USING (SELECT ? AS store_id, ? AS week_from) AS source
            ON target.store_id=source.store_id AND target.week_from=source.week_from
            WHEN MATCHED AND target.status NOT IN (N'approved',N'locked') THEN UPDATE SET
                status=N'failed', error_summary=?, calculation_version=?, updated_at=SYSDATETIMEOFFSET()
            WHEN NOT MATCHED THEN INSERT
                (store_id, employer_afm, branch_aa, week_from, week_to, status, calculation_version, error_summary)
                VALUES (?, ?, ?, ?, ?, N'failed', ?, ?);
        """, (int(store["id"]), week_from, str(error)[:2000], calculation_version,
              int(store["id"]), store["employer_afm"], store["branch_aa"], week_from, week_to,
              calculation_version, str(error)[:2000]))


def load_report(store_id: int, week_from: date) -> tuple[dict[str, Any], dict[str, Any]] | None:
    run = get_run(store_id, week_from)
    if not run or not run.get("effective_report_json"):
        return None
    report = json.loads(run["effective_report_json"])
    with cursor(commit=False) as cur:
        cur.execute("""
            SELECT d.employee_afm, d.work_date, c.old_value, c.new_value, c.changed_by,
                   CAST(c.changed_at AS datetime2) AS changed_at
            FROM dbo.karta_apologistic_change c
            INNER JOIN dbo.karta_apologistic_day d ON d.id=c.day_id
            WHERE d.run_id=? AND c.field_name=N'proposed'
            ORDER BY c.changed_at DESC, c.id DESC
        """, (int(run["id"]),))
        histories: dict[tuple[str, str], list[dict[str, Any]]] = {}
        for row in cur.fetchall():
            key = (str(row[0]), row[1].strftime("%d/%m/%Y"))
            histories.setdefault(key, []).append({
                "old_value": row[2], "new_value": row[3], "changed_by": row[4],
                "changed_at": row[5].isoformat(timespec="seconds") if row[5] else None,
            })
        cur.execute("""
            SELECT employee_afm, source_work_date, source_actual_minutes, source_punch_days,
                   target_week_from, target_week_to, status
            FROM dbo.karta_apologistic_rest_obligation
            WHERE store_id=? AND target_week_from=? AND status=N'pending'
            ORDER BY employee_afm, source_work_date
        """, (int(store_id), week_from))
        rest_due_by_afm: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in cur.fetchall():
            rest_due_by_afm[str(row[0])].append({
                "source_work_date": row[1].strftime("%d/%m/%Y"),
                "source_actual_minutes": int(row[2]),
                "source_punch_days": int(row[3]),
                "target_week_from": row[4].isoformat(),
                "target_week_to": row[5].isoformat(),
                "status": str(row[6]),
            })
    for day in report.get("days") or []:
        day["proposal_history"] = histories.get((str(day.get("employee_afm") or ""), str(day.get("work_date") or "")), [])
        day["incoming_rest_obligations"] = rest_due_by_afm.get(str(day.get("employee_afm") or ""), [])
    _attach_ergani_submits(int(run["id"]), report)
    _attach_ergani_submits_from_declarations(
        int(run["id"]),
        int(store_id),
        week_from,
        run.get("week_to") or week_from,
        str(run.get("employer_afm") or ""),
        report,
    )
    report["rest_obligations"] = [
        {"employee_afm": afm, **item}
        for afm, items in rest_due_by_afm.items() for item in items
    ]
    meta = {k: run.get(k) for k in ("id", "status", "calculation_version", "started_at", "completed_at", "updated_at")}
    return report, meta


def list_employee_days(*, store_id: int, employee_afm: str,
                       date_from: date, date_to: date) -> list[dict[str, Any]]:
    """Effective (including manual overrides) retrospective rows for a month view."""
    with cursor(commit=False) as cur:
        cur.execute("""
            SELECT d.id, d.work_date, d.effective_json, r.id, r.week_from, r.week_to,
                   r.status, r.calculation_version,
                   CAST(r.completed_at AS datetime2) AS completed_at
            FROM dbo.karta_apologistic_day d
            INNER JOIN dbo.karta_apologistic_run r ON r.id=d.run_id
            WHERE r.store_id=? AND d.employee_afm=?
              AND d.work_date BETWEEN ? AND ?
              AND r.status IN (N'draft', N'approved', N'locked')
            ORDER BY d.work_date
        """, (int(store_id), employee_afm, date_from, date_to))
        rows: list[dict[str, Any]] = []
        for record in cur.fetchall():
            try:
                item = json.loads(record[2])
            except (TypeError, json.JSONDecodeError):
                continue
            item["source"] = "snapshot"
            item["finalized"] = True
            item["day_id"] = int(record[0])
            item["run_id"] = int(record[3])
            item["week_from"] = record[4].isoformat()
            item["week_to"] = record[5].isoformat()
            item["run_status"] = str(record[6])
            item["calculation_version"] = str(record[7])
            item["completed_at"] = record[8].isoformat() if record[8] else None
            rows.append(item)
        return rows


def list_store_days(*, store_id: int, date_from: date, date_to: date) -> list[dict[str, Any]]:
    """Effective retrospective rows for all employees in a calendar range."""
    with cursor(commit=False) as cur:
        cur.execute("""
            SELECT d.id, d.work_date, d.effective_json, r.id, r.week_from, r.week_to,
                   r.status, r.calculation_version,
                   CAST(r.completed_at AS datetime2) AS completed_at
            FROM dbo.karta_apologistic_day d
            INNER JOIN dbo.karta_apologistic_run r ON r.id=d.run_id
            WHERE r.store_id=? AND d.work_date BETWEEN ? AND ?
              AND r.status IN (N'draft', N'approved', N'locked')
            ORDER BY d.work_date, d.employee_afm
        """, (int(store_id), date_from, date_to))
        rows: list[dict[str, Any]] = []
        for record in cur.fetchall():
            try:
                item = json.loads(record[2])
            except (TypeError, json.JSONDecodeError):
                continue
            item.update({
                "source": "snapshot", "finalized": True,
                "day_id": int(record[0]), "run_id": int(record[3]),
                "week_from": record[4].isoformat(), "week_to": record[5].isoformat(),
                "run_status": str(record[6]), "calculation_version": str(record[7]),
                "completed_at": record[8].isoformat() if record[8] else None,
            })
            rows.append(item)
        return rows


def enrich_employee_month_days(
    *,
    store_id: int,
    employer_afm: str,
    branch_aa: str,
    days: list[dict[str, Any]],
) -> None:
    """Attach proposal history and Ergani submit state to finalized month rows."""
    finalized = [day for day in days if day.get("finalized") and day.get("run_id")]
    if not finalized:
        return

    day_ids = [int(day["day_id"]) for day in finalized if day.get("day_id")]
    histories: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    if day_ids:
        placeholders = ",".join("?" * len(day_ids))
        with cursor(commit=False) as cur:
            cur.execute(
                f"""
                SELECT d.employee_afm, d.work_date, c.old_value, c.new_value, c.changed_by,
                       CAST(c.changed_at AS datetime2) AS changed_at
                FROM dbo.karta_apologistic_change c
                INNER JOIN dbo.karta_apologistic_day d ON d.id=c.day_id
                WHERE c.day_id IN ({placeholders}) AND c.field_name=N'proposed'
                ORDER BY c.changed_at DESC, c.id DESC
                """,
                day_ids,
            )
            for row in cur.fetchall():
                key = (str(row[0]), row[1].strftime("%d/%m/%Y"))
                histories[key].append({
                    "old_value": row[2],
                    "new_value": row[3],
                    "changed_by": row[4],
                    "changed_at": row[5].isoformat(timespec="seconds") if row[5] else None,
                })

    runs: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for day in finalized:
        runs[int(day["run_id"])].append(day)

    for run_id, run_days in runs.items():
        mini_report = {"days": run_days}
        _attach_ergani_submits(run_id, mini_report)
        week_from_raw = str(run_days[0].get("week_from") or "")[:10]
        week_to_raw = str(run_days[0].get("week_to") or "")[:10]
        try:
            week_from = datetime.strptime(week_from_raw, "%Y-%m-%d").date()
            week_to = datetime.strptime(week_to_raw, "%Y-%m-%d").date()
        except ValueError:
            continue
        _attach_ergani_submits_from_declarations(
            run_id,
            int(store_id),
            week_from,
            week_to,
            str(employer_afm or ""),
            mini_report,
        )

    for day in finalized:
        key = (str(day.get("employee_afm") or ""), str(day.get("work_date") or ""))
        day["proposal_history"] = histories.get(key, [])


def update_proposed(*, store_id: int, week_from: date, employee_afm: str,
                    work_date: date, proposed: str, changed_by: str | None) -> dict[str, Any]:
    value = normalize_proposed_value(proposed)
    with cursor(commit=True) as cur:
        cur.execute("""
            SELECT d.id, d.override_json, d.effective_json, r.id, r.status, r.effective_report_json
            FROM dbo.karta_apologistic_day d WITH (UPDLOCK, HOLDLOCK)
            INNER JOIN dbo.karta_apologistic_run r ON r.id=d.run_id
            WHERE r.store_id=? AND r.week_from=? AND d.employee_afm=? AND d.work_date=?
        """, (int(store_id), week_from, employee_afm, work_date))
        row = cur.fetchone()
        if not row:
            raise LookupError("Δεν βρέθηκε αποθηκευμένο ημερήσιο αποτέλεσμα")
        if str(row[4]) == "locked":
            raise PermissionError("Η εβδομάδα είναι κλειδωμένη")
        day_id, run_id = int(row[0]), int(row[3])
        override = json.loads(row[1]) if row[1] else {}
        effective = json.loads(row[2])
        old_value = str(effective.get("proposed") or "")
        if old_value == value:
            return {"proposed": value, "changed": False, "status": effective.get("status"),
                    "reason": effective.get("reason"), "status_changed": False}
        override["proposed"] = value
        effective["proposed"] = value
        status_changed = False
        if str(effective.get("status") or "") == "review":
            override["status"] = "change"
            effective["status"] = "change"
            effective["reason"] = "Χειροκίνητη πρόταση — μετατράπηκε από Έλεγχο σε Μεταβολή"
            override.pop("change_from_review", None)
            effective.pop("change_from_review", None)
            status_changed = True
        report = json.loads(row[5])
        for item in report.get("days") or []:
            if str(item.get("employee_afm") or "") == employee_afm and str(item.get("work_date") or "") == work_date.strftime("%d/%m/%Y"):
                item["proposed"] = value
                if status_changed:
                    item["status"] = "change"
                    item["reason"] = effective["reason"]
                    item.pop("change_from_review", None)
                break
        if status_changed and isinstance(report.get("counts"), dict):
            counts = report["counts"]
            counts["review"] = max(0, int(counts.get("review") or 0) - 1)
            counts["change"] = int(counts.get("change") or 0) + 1
        cur.execute("""
            UPDATE dbo.karta_apologistic_day SET override_json=?, effective_json=?,
                override_reason=N'Χειροκίνητη αλλαγή προτεινόμενου ωραρίου', updated_by=?,
                override_updated_at=SYSDATETIMEOFFSET(), updated_at=SYSDATETIMEOFFSET()
            WHERE id=?
        """, (_json(override), _json(effective), changed_by, day_id))
        cur.execute("""
            INSERT dbo.karta_apologistic_change(day_id, field_name, old_value, new_value, changed_by)
            VALUES (?, N'proposed', ?, ?, ?)
        """, (day_id, old_value, value, changed_by))
        cur.execute("UPDATE dbo.karta_apologistic_run SET effective_report_json=?, updated_at=SYSDATETIMEOFFSET() WHERE id=?",
                    (_json(report), run_id))
    return {
        "proposed": value,
        "changed": True,
        "status": effective.get("status"),
        "reason": effective.get("reason"),
        "status_changed": status_changed,
        "change_from_review": bool(effective.get("change_from_review")),
    }


def accept_review(*, store_id: int, week_from: date, employee_afm: str,
                  work_date: date, changed_by: str | None) -> dict[str, Any]:
    with cursor(commit=True) as cur:
        cur.execute("""
            SELECT d.id, d.override_json, d.effective_json, r.id, r.status, r.effective_report_json
            FROM dbo.karta_apologistic_day d WITH (UPDLOCK, HOLDLOCK)
            INNER JOIN dbo.karta_apologistic_run r ON r.id=d.run_id
            WHERE r.store_id=? AND r.week_from=? AND d.employee_afm=? AND d.work_date=?
        """, (int(store_id), week_from, employee_afm, work_date))
        row = cur.fetchone()
        if not row:
            raise LookupError("Δεν βρέθηκε αποθηκευμένο ημερήσιο αποτέλεσμα")
        if str(row[4]) == "locked":
            raise PermissionError("Η εβδομάδα είναι κλειδωμένη")
        day_id, run_id = int(row[0]), int(row[3])
        override = json.loads(row[1]) if row[1] else {}
        effective = json.loads(row[2])
        if (effective.get("uneven_distribution_group") or {}).get("group_id"):
            raise ValueError("Η ανισομερής κατανομή πρέπει να εγκριθεί ως ενιαία ομάδα")
        old_status = str(effective.get("status") or "")
        if old_status == "change" and effective.get("change_from_review"):
            return {
                "status": "change",
                "change_from_review": True,
                "changed": False,
                "reason": effective.get("reason"),
                "proposed": effective.get("proposed"),
                "counts": None,
            }
        if old_status != "review":
            raise ValueError("Η εγγραφή δεν είναι σε κατάσταση Έλεγχος")
        override["status"] = "change"
        override["change_from_review"] = True
        effective["status"] = "change"
        effective["change_from_review"] = True
        effective["reason"] = "Εγκρίθηκε η πρόταση — μετατράπηκε από Έλεγχο σε Μεταβολή"
        report = json.loads(row[5])
        for item in report.get("days") or []:
            if str(item.get("employee_afm") or "") == employee_afm and str(item.get("work_date") or "") == work_date.strftime("%d/%m/%Y"):
                item["status"] = "change"
                item["change_from_review"] = True
                item["reason"] = effective["reason"]
                break
        if isinstance(report.get("counts"), dict):
            counts = report["counts"]
            counts["review"] = max(0, int(counts.get("review") or 0) - 1)
            counts["change"] = int(counts.get("change") or 0) + 1
        cur.execute("""
            UPDATE dbo.karta_apologistic_day SET override_json=?, effective_json=?,
                override_reason=N'Έγκριση πρότασης από Έλεγχο', updated_by=?,
                override_updated_at=SYSDATETIMEOFFSET(), updated_at=SYSDATETIMEOFFSET()
            WHERE id=?
        """, (_json(override), _json(effective), changed_by, day_id))
        cur.execute("""
            INSERT dbo.karta_apologistic_change(day_id, field_name, old_value, new_value, changed_by)
            VALUES (?, N'status', ?, ?, ?)
        """, (day_id, "review", "change", changed_by))
        cur.execute("UPDATE dbo.karta_apologistic_run SET effective_report_json=?, updated_at=SYSDATETIMEOFFSET() WHERE id=?",
                    (_json(report), run_id))
    return {
        "status": "change",
        "change_from_review": True,
        "changed": True,
        "reason": effective["reason"],
        "proposed": effective.get("proposed"),
        "counts": report.get("counts"),
    }


def accept_uneven_distribution_group(
    *, store_id: int, week_from: date, employee_afm: str,
    group_id: str, changed_by: str | None,
) -> dict[str, Any]:
    """Approve every member of one balanced distribution in one transaction."""
    group_id = str(group_id or "").strip()
    if not group_id.startswith("UD-"):
        raise ValueError("Μη έγκυρη ομάδα ανισομερούς κατανομής")
    reason = "Εγκρίθηκε ολόκληρη η ομάδα ανισομερούς κατανομής"
    with cursor(commit=True) as cur:
        cur.execute("""
            SELECT r.id, r.status, r.effective_report_json
            FROM dbo.karta_apologistic_run r WITH (UPDLOCK, HOLDLOCK)
            WHERE r.store_id=? AND r.week_from=?
        """, (int(store_id), week_from))
        run_row = cur.fetchone()
        if not run_row:
            raise LookupError("Δεν βρέθηκε αποθηκευμένο απολογιστικό")
        if str(run_row[1]) == "locked":
            raise PermissionError("Η εβδομάδα είναι κλειδωμένη")
        run_id = int(run_row[0])
        report = json.loads(run_row[2])
        report_members = [
            item for item in report.get("days") or []
            if str(item.get("employee_afm") or "") == employee_afm
            and str((item.get("uneven_distribution_group") or {}).get("group_id") or "") == group_id
        ]
        if not report_members:
            raise LookupError("Δεν βρέθηκε η ομάδα ανισομερούς κατανομής")
        group = report_members[0].get("uneven_distribution_group") or {}
        if int(group.get("balance_minutes") or 0) != 0:
            raise ValueError("Η ομάδα δεν έχει μηδενικό ισοζύγιο")
        expected_dates = {str(item.get("work_date") or "") for item in group.get("members") or []}
        actual_dates = {str(item.get("work_date") or "") for item in report_members}
        if not expected_dates or actual_dates != expected_dates:
            raise ValueError("Η ομάδα ανισομερούς κατανομής είναι ελλιπής")

        changed = 0
        for item in report_members:
            work_date_str = str(item.get("work_date") or "")
            work_date = datetime.strptime(work_date_str, "%d/%m/%Y").date()
            cur.execute("""
                SELECT d.id, d.override_json, d.effective_json
                FROM dbo.karta_apologistic_day d WITH (UPDLOCK, HOLDLOCK)
                WHERE d.run_id=? AND d.employee_afm=? AND d.work_date=?
            """, (run_id, employee_afm, work_date))
            day_row = cur.fetchone()
            if not day_row:
                raise LookupError(f"Λείπει η ημέρα {work_date_str} από την ομάδα")
            day_id = int(day_row[0])
            override = json.loads(day_row[1]) if day_row[1] else {}
            effective = json.loads(day_row[2])
            persisted_group = effective.get("uneven_distribution_group") or {}
            if str(persisted_group.get("group_id") or "") != group_id:
                raise ValueError("Η αποθηκευμένη ομάδα δεν συμφωνεί με την πρόταση")
            old_status = str(effective.get("status") or "")
            if old_status == "change" and effective.get("change_from_review"):
                continue
            if old_status != "review":
                raise ValueError(f"Η ημέρα {work_date_str} δεν βρίσκεται σε κατάσταση Έλεγχος")
            override.update({"status": "change", "change_from_review": True})
            effective.update({"status": "change", "change_from_review": True, "reason": reason})
            item.update({"status": "change", "change_from_review": True, "reason": reason})
            cur.execute("""
                UPDATE dbo.karta_apologistic_day SET override_json=?, effective_json=?,
                    override_reason=N'Έγκριση ομάδας ανισομερούς κατανομής', updated_by=?,
                    override_updated_at=SYSDATETIMEOFFSET(), updated_at=SYSDATETIMEOFFSET()
                WHERE id=?
            """, (_json(override), _json(effective), changed_by, day_id))
            cur.execute("""
                INSERT dbo.karta_apologistic_change(day_id, field_name, old_value, new_value, changed_by)
                VALUES (?, N'uneven_distribution_group', ?, ?, ?)
            """, (day_id, old_status, "change", changed_by))
            changed += 1
        if changed and isinstance(report.get("counts"), dict):
            report["counts"]["review"] = max(0, int(report["counts"].get("review") or 0) - changed)
            report["counts"]["change"] = int(report["counts"].get("change") or 0) + changed
        if changed:
            cur.execute(
                "UPDATE dbo.karta_apologistic_run SET effective_report_json=?, updated_at=SYSDATETIMEOFFSET() WHERE id=?",
                (_json(report), run_id),
            )
    return {"changed": changed, "group_id": group_id, "counts": report.get("counts"), "days": report_members}


def apply_exchange(*, store_id: int, week_from: date, employee_afm: str,
                   rest_work_date: date, replacement_work_date: date,
                   changed_by: str | None) -> dict[str, Any]:
    """Apply both sides of a proposed rest/work-day exchange in one transaction."""
    if rest_work_date == replacement_work_date:
        raise ValueError("Οι δύο ημέρες της ανταλλαγής πρέπει να είναι διαφορετικές")
    rest_label = rest_work_date.strftime("%d/%m/%Y")
    replacement_label = replacement_work_date.strftime("%d/%m/%Y")
    reason = "Εγκρίθηκε ανταλλαγή ημέρας — δημιουργήθηκαν δύο απολογιστικές μεταβολές"
    with cursor(commit=True) as cur:
        cur.execute("""
            SELECT r.id, r.status, r.effective_report_json
            FROM dbo.karta_apologistic_run r WITH (UPDLOCK, HOLDLOCK)
            WHERE r.store_id=? AND r.week_from=?
        """, (int(store_id), week_from))
        run_row = cur.fetchone()
        if not run_row:
            raise LookupError("Δεν βρέθηκε αποθηκευμένο απολογιστικό")
        if str(run_row[1]) == "locked":
            raise PermissionError("Η εβδομάδα είναι κλειδωμένη")
        run_id = int(run_row[0])
        report = json.loads(run_row[2])

        cur.execute("""
            SELECT d.id, d.work_date, d.override_json, d.effective_json
            FROM dbo.karta_apologistic_day d WITH (UPDLOCK, HOLDLOCK)
            WHERE d.run_id=? AND d.employee_afm=? AND d.work_date IN (?, ?)
        """, (run_id, employee_afm, rest_work_date, replacement_work_date))
        rows = list(cur.fetchall())
        by_date = {
            (row[1].date() if isinstance(row[1], datetime) else row[1]): row
            for row in rows
        }
        source_row = by_date.get(rest_work_date)
        target_row = by_date.get(replacement_work_date)
        if not source_row or not target_row:
            raise LookupError("Δεν βρέθηκαν και οι δύο ημέρες της ανταλλαγής")

        source = json.loads(source_row[3])
        target = json.loads(target_row[3])
        options = source.get("exchange_options") or []
        option = next((item for item in options
                       if str(item.get("replacement_work_date") or "") == replacement_label), None)
        if not option:
            raise ValueError("Η επιλεγμένη ημέρα δεν είναι διαθέσιμη πρόταση ανταλλαγής")
        if str(source.get("status") or "") not in {"review", "change"}:
            raise ValueError("Η αρχική ημέρα δεν βρίσκεται σε κατάσταση Έλεγχος")
        existing_pair = target.get("exchange_pair") or {}
        if existing_pair and str(existing_pair.get("paired_work_date") or "") != rest_label:
            raise ValueError("Η ημέρα αντικατάστασης έχει ήδη χρησιμοποιηθεί σε άλλη ανταλλαγή")

        source_proposed = normalize_proposed_value(str(option.get("proposed") or ""))
        target_proposed = "ΑΝΑΠΑΥΣΗ/ΡΕΠΟ"
        pair_id = f"{employee_afm}:{rest_label}:{replacement_label}"
        source_pair = {"id": pair_id, "role": "work", "paired_work_date": replacement_label}
        target_pair = {"id": pair_id, "role": "rest", "paired_work_date": rest_label}
        source_override = json.loads(source_row[2]) if source_row[2] else {}
        target_override = json.loads(target_row[2]) if target_row[2] else {}

        source_old_status = str(source.get("status") or "")
        target_old_status = str(target.get("status") or "")
        source.update({"proposed": source_proposed, "status": "change", "change_from_review": True,
                       "day_state": "Εργασία", "reason": reason, "exchange_pair": source_pair,
                       "exchange_options": [], "replacement_candidates": []})
        target.update({"proposed": target_proposed, "status": "change", "change_from_review": True,
                       "day_state": "Ρεπό", "reason": reason, "exchange_pair": target_pair})
        source_override.update({"proposed": source_proposed, "status": "change", "change_from_review": True,
                                "day_state": "Εργασία", "exchange_pair": source_pair})
        target_override.update({"proposed": target_proposed, "status": "change", "change_from_review": True,
                                "day_state": "Ρεπό", "exchange_pair": target_pair})

        updates = ((source_row, source_override, source, source_old_status, source_proposed),
                   (target_row, target_override, target, target_old_status, target_proposed))
        for db_row, override, effective, old_status, proposed in updates:
            cur.execute("""
                UPDATE dbo.karta_apologistic_day SET override_json=?, effective_json=?,
                    override_reason=N'Ανταλλαγή ημέρας εργασίας/ρεπό', updated_by=?,
                    override_updated_at=SYSDATETIMEOFFSET(), updated_at=SYSDATETIMEOFFSET()
                WHERE id=?
            """, (_json(override), _json(effective), changed_by, int(db_row[0])))
            cur.execute("""
                INSERT dbo.karta_apologistic_change(day_id, field_name, old_value, new_value, changed_by)
                VALUES (?, N'exchange', ?, ?, ?)
            """, (int(db_row[0]), old_status, proposed, changed_by))

        effective_by_date = {rest_label: source, replacement_label: target}
        for item in report.get("days") or []:
            if str(item.get("employee_afm") or "") != employee_afm:
                continue
            updated = effective_by_date.get(str(item.get("work_date") or ""))
            if updated:
                item.update(updated)
        if isinstance(report.get("counts"), dict):
            counts = report["counts"]
            old_statuses = (source_old_status, target_old_status)
            for old_status in old_statuses:
                if old_status != "change":
                    counts[old_status] = max(0, int(counts.get(old_status) or 0) - 1)
                    counts["change"] = int(counts.get("change") or 0) + 1
        cur.execute(
            "UPDATE dbo.karta_apologistic_run SET effective_report_json=?, updated_at=SYSDATETIMEOFFSET() WHERE id=?",
            (_json(report), run_id),
        )
    return {"changed": True, "rows": [source, target], "counts": report.get("counts")}


def accept_all_review(*, store_id: int, week_from: date,
                      items: list[dict[str, Any]], changed_by: str | None) -> dict[str, Any]:
    if not items:
        raise ValueError("Δεν υπάρχουν εγγραφές για έγκριση")
    reason = "Εγκρίθηκε η πρόταση — μετατράπηκε από Έλεγχο σε Μεταβολή"
    changed = 0
    skipped = 0
    with cursor(commit=True) as cur:
        cur.execute("""
            SELECT r.id, r.status, r.effective_report_json
            FROM dbo.karta_apologistic_run r WITH (UPDLOCK, HOLDLOCK)
            WHERE r.store_id=? AND r.week_from=?
        """, (int(store_id), week_from))
        run_row = cur.fetchone()
        if not run_row:
            raise LookupError("Δεν βρέθηκε αποθηκευμένο απολογιστικό")
        if str(run_row[1]) == "locked":
            raise PermissionError("Η εβδομάδα είναι κλειδωμένη")
        run_id = int(run_row[0])
        report = json.loads(run_row[2])

        requested = {
            (str(item.get("employee_afm") or "").strip(), str(item.get("work_date") or "").strip())
            for item in items if isinstance(item, dict)
        }
        requested_groups = {
            (str(day.get("employee_afm") or ""), str(group.get("group_id") or ""))
            for day in report.get("days") or []
            for group in [day.get("uneven_distribution_group") or {}]
            if (str(day.get("employee_afm") or ""), str(day.get("work_date") or "")) in requested
            and str(group.get("group_id") or "").startswith("UD-")
        }
        for day in report.get("days") or []:
            key = (str(day.get("employee_afm") or ""), str(day.get("work_date") or ""))
            group_id = str((day.get("uneven_distribution_group") or {}).get("group_id") or "")
            if (key[0], group_id) in requested_groups:
                requested.add(key)
        items = [{"employee_afm": afm, "work_date": work_date} for afm, work_date in sorted(requested)]

        for raw in items:
            employee_afm = str(raw.get("employee_afm") or "").strip()
            work_date_str = str(raw.get("work_date") or "").strip()
            try:
                work_date = datetime.strptime(work_date_str, "%d/%m/%Y").date()
            except ValueError:
                skipped += 1
                continue
            if len(employee_afm) != 9 or not employee_afm.isdigit():
                skipped += 1
                continue

            cur.execute("""
                SELECT d.id, d.override_json, d.effective_json
                FROM dbo.karta_apologistic_day d WITH (UPDLOCK, HOLDLOCK)
                WHERE d.run_id=? AND d.employee_afm=? AND d.work_date=?
            """, (run_id, employee_afm, work_date))
            day_row = cur.fetchone()
            if not day_row:
                skipped += 1
                continue

            day_id = int(day_row[0])
            override = json.loads(day_row[1]) if day_row[1] else {}
            effective = json.loads(day_row[2])
            old_status = str(effective.get("status") or "")
            if old_status == "change" and effective.get("change_from_review"):
                skipped += 1
                continue
            if old_status != "review":
                skipped += 1
                continue

            override["status"] = "change"
            override["change_from_review"] = True
            effective["status"] = "change"
            effective["change_from_review"] = True
            effective["reason"] = reason
            for day_item in report.get("days") or []:
                if (str(day_item.get("employee_afm") or "") == employee_afm
                        and str(day_item.get("work_date") or "") == work_date_str):
                    day_item["status"] = "change"
                    day_item["change_from_review"] = True
                    day_item["reason"] = reason
                    break

            cur.execute("""
                UPDATE dbo.karta_apologistic_day SET override_json=?, effective_json=?,
                    override_reason=N'Έγκριση πρότασης από Έλεγχο', updated_by=?,
                    override_updated_at=SYSDATETIMEOFFSET(), updated_at=SYSDATETIMEOFFSET()
                WHERE id=?
            """, (_json(override), _json(effective), changed_by, day_id))
            cur.execute("""
                INSERT dbo.karta_apologistic_change(day_id, field_name, old_value, new_value, changed_by)
                VALUES (?, N'status', ?, ?, ?)
            """, (day_id, "review", "change", changed_by))
            changed += 1

        if isinstance(report.get("counts"), dict) and changed:
            counts = report["counts"]
            counts["review"] = max(0, int(counts.get("review") or 0) - changed)
            counts["change"] = int(counts.get("change") or 0) + changed
        if changed:
            cur.execute(
                "UPDATE dbo.karta_apologistic_run SET effective_report_json=?, updated_at=SYSDATETIMEOFFSET() WHERE id=?",
                (_json(report), run_id),
            )

    if changed == 0:
        raise ValueError("Δεν βρέθηκαν εγγραφές σε κατάσταση Έλεγχος")
    return {"changed": changed, "skipped": skipped, "counts": report.get("counts")}


def submit_table_available() -> bool:
    try:
        with cursor(commit=False) as cur:
            cur.execute(f"SELECT OBJECT_ID(N'dbo.{_SUBMIT_TABLE}', N'U')")
            return bool(cur.fetchone()[0])
    except Exception:
        return False


def get_day_id(*, store_id: int, week_from: date, employee_afm: str, work_date: date) -> int | None:
    with cursor(commit=False) as cur:
        cur.execute("""
            SELECT d.id
            FROM dbo.karta_apologistic_day d
            INNER JOIN dbo.karta_apologistic_run r ON r.id = d.run_id
            WHERE r.store_id = ? AND r.week_from = ? AND d.employee_afm = ? AND d.work_date = ?
        """, (int(store_id), week_from, employee_afm, work_date))
        row = cur.fetchone()
        return int(row[0]) if row else None


def _submit_entry_from_row(record: dict[str, Any], *, proposed: str | None = None) -> dict[str, Any]:
    submitted_at = record.get("submitted_at")
    if hasattr(submitted_at, "isoformat"):
        submitted_at = submitted_at.isoformat(timespec="seconds")
    entry = {
        "protocol": record.get("protocol"),
        "ergani_submission_id": record.get("ergani_submission_id"),
        "submit_date": record.get("submit_date_text"),
        "submitted_at": submitted_at,
        "declaration_id": record.get("declaration_id"),
        "proposed_at_submit": record.get("proposed_at_submit"),
        "segment_date": record.get("segment_date"),
    }
    if proposed is not None and record.get("proposed_at_submit"):
        entry["matches_proposal"] = str(record.get("proposed_at_submit") or "").strip() == str(proposed or "").strip()
    return entry


def _attach_ergani_submits(run_id: int, report: dict[str, Any]) -> None:
    if not submit_table_available():
        return
    with cursor(commit=False) as cur:
        cur.execute("""
            SELECT d.employee_afm, d.work_date, d.effective_json,
                   s.submission_code, s.proposed_at_submit, s.segment_reference_date,
                   s.protocol, s.ergani_submission_id, s.submit_date_text, s.declaration_id,
                   CAST(s.submitted_at AS datetime2) AS submitted_at
            FROM dbo.karta_apologistic_submit s
            INNER JOIN dbo.karta_apologistic_day d ON d.id = s.day_id
            WHERE d.run_id = ? AND s.success = 1
            ORDER BY s.submitted_at DESC, s.id DESC
        """, (int(run_id),))
        rows = rows_to_dicts(cur)
    latest: dict[tuple[str, str, str, str | None], dict[str, Any]] = {}
    for row in rows:
        seg = row.get("segment_reference_date")
        seg_key = seg.strftime("%d/%m/%Y") if hasattr(seg, "strftime") else (str(seg)[:10] if seg else None)
        key = (
            str(row.get("employee_afm") or ""),
            row.get("work_date").strftime("%d/%m/%Y") if hasattr(row.get("work_date"), "strftime") else str(row.get("work_date") or ""),
            str(row.get("submission_code") or ""),
            seg_key,
        )
        if key in latest:
            continue
        item = dict(row)
        item["segment_date"] = seg_key
        latest[key] = item
    for day in report.get("days") or []:
        afm = str(day.get("employee_afm") or "")
        wd = str(day.get("work_date") or "")
        proposed = str(day.get("proposed") or "")
        ergani_submit: dict[str, Any] = {}
        schedule = latest.get((afm, wd, SUBMISSION_CODE_WTO_DAILY_A, None))
        if schedule:
            ergani_submit["schedule"] = _submit_entry_from_row(schedule, proposed=proposed)
        overtime: dict[str, Any] = {}
        for (key_afm, key_wd, code, seg_date), record in latest.items():
            if key_afm != afm or key_wd != wd or code != SUBMISSION_CODE_WTO_OV_A or not seg_date:
                continue
            overtime[seg_date] = _submit_entry_from_row(record)
        if overtime:
            ergani_submit["overtime"] = overtime
        if ergani_submit:
            day["ergani_submit"] = ergani_submit


def _merge_day_ergani_submit(day: dict[str, Any], fragment: dict[str, Any]) -> None:
    if not fragment:
        return
    current = day.setdefault("ergani_submit", {})
    if fragment.get("schedule") and not current.get("schedule"):
        current["schedule"] = fragment["schedule"]
    if fragment.get("overtime"):
        bucket = current.setdefault("overtime", {})
        for seg_date, entry in fragment["overtime"].items():
            if seg_date and not bucket.get(seg_date):
                bucket[seg_date] = entry


def _attach_ergani_submits_from_declarations(
    run_id: int,
    store_id: int,
    week_from: date,
    week_to: date,
    employer_afm: str,
    report: dict[str, Any],
) -> None:
    if not employer_afm:
        return
    week_days = {
        (str(day.get("employee_afm") or ""), str(day.get("work_date") or ""))
        for day in (report.get("days") or [])
    }
    if not week_days:
        return
    with cursor(commit=False) as cur:
        cur.execute(
            """
            SELECT id, submission_code, protocol, ergani_submission_id, submit_date_text,
                   request_json, CAST(created_at AS datetime2) AS created_at
            FROM dbo.karta_declaration
            WHERE employer_afm = ? AND success = 1
              AND submission_code IN (?, ?)
              AND created_at >= DATEADD(day, -21, SYSDATETIMEOFFSET())
            ORDER BY id DESC
            """,
            (employer_afm, SUBMISSION_CODE_WTO_DAILY_A, SUBMISSION_CODE_WTO_OV_A),
        )
        declarations = rows_to_dicts(cur)
    latest_decl: dict[tuple[str, str, str], dict[str, Any]] = {}
    for item in declarations:
        afm, work_date, proposed = parse_wto_request_meta(item.get("request_json"))
        if not afm or not work_date or (afm, work_date) not in week_days:
            continue
        try:
            wd = datetime.strptime(work_date, "%d/%m/%Y").date()
        except ValueError:
            continue
        if wd < week_from or wd > week_to:
            continue
        code = str(item.get("submission_code") or "")
        key = (afm, work_date, code)
        if key in latest_decl:
            continue
        submitted_at = item.get("created_at")
        if hasattr(submitted_at, "isoformat"):
            submitted_at = submitted_at.isoformat(timespec="seconds")
        latest_decl[key] = {
            "protocol": item.get("protocol"),
            "ergani_submission_id": item.get("ergani_submission_id"),
            "submit_date": item.get("submit_date_text"),
            "submitted_at": submitted_at,
            "declaration_id": item.get("id"),
            "proposed_at_submit": proposed,
            "segment_date": work_date if code == SUBMISSION_CODE_WTO_OV_A else None,
        }
    if not latest_decl:
        return
    for day in report.get("days") or []:
        afm = str(day.get("employee_afm") or "")
        wd = str(day.get("work_date") or "")
        proposed = str(day.get("proposed") or "")
        schedule_key = (afm, wd, SUBMISSION_CODE_WTO_DAILY_A)
        if schedule_key in latest_decl and not (day.get("ergani_submit") or {}).get("schedule"):
            entry = dict(latest_decl[schedule_key])
            if entry.get("proposed_at_submit"):
                entry["matches_proposal"] = str(entry["proposed_at_submit"]).strip() == proposed.strip()
            _merge_day_ergani_submit(day, {"schedule": entry})
            _ensure_submit_row_from_declaration(
                run_id, store_id, week_from, afm, wd, SUBMISSION_CODE_WTO_DAILY_A,
                latest_decl[schedule_key], proposed_at_submit=entry.get("proposed_at_submit"),
            )
        ot_key = (afm, wd, SUBMISSION_CODE_WTO_OV_A)
        if ot_key in latest_decl:
            ot = (day.get("ergani_submit") or {}).get("overtime") or {}
            seg = wd
            if not ot.get(seg):
                entry = dict(latest_decl[ot_key])
                entry["segment_date"] = seg
                _merge_day_ergani_submit(day, {"overtime": {seg: entry}})
                _ensure_submit_row_from_declaration(
                    run_id, store_id, week_from, afm, wd, SUBMISSION_CODE_WTO_OV_A,
                    latest_decl[ot_key], segment_reference_date=datetime.strptime(wd, "%d/%m/%Y").date(),
                )


def _ensure_submit_row_from_declaration(
    run_id: int,
    store_id: int,
    week_from: date,
    employee_afm: str,
    work_date_str: str,
    submission_code: str,
    entry: dict[str, Any],
    *,
    proposed_at_submit: str | None = None,
    segment_reference_date: date | None = None,
) -> None:
    if not submit_table_available():
        return
    try:
        work_date = datetime.strptime(work_date_str, "%d/%m/%Y").date()
    except ValueError:
        return
    day_id = get_day_id(store_id=store_id, week_from=week_from, employee_afm=employee_afm, work_date=work_date)
    if not day_id or not entry.get("declaration_id"):
        return
    with cursor(commit=True) as cur:
        cur.execute(
            f"""
            SELECT TOP 1 1 FROM dbo.{_SUBMIT_TABLE}
            WHERE day_id = ? AND submission_code = ? AND declaration_id = ?
            """,
            (int(day_id), submission_code, int(entry["declaration_id"])),
        )
        if cur.fetchone():
            return
        cur.execute(
            f"""
            INSERT dbo.{_SUBMIT_TABLE}
                (day_id, submission_code, declaration_id, proposed_at_submit, segment_reference_date,
                 protocol, ergani_submission_id, submit_date_text, success)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)
            """,
            (
                int(day_id),
                submission_code,
                int(entry["declaration_id"]),
                (str(proposed_at_submit).strip()[:64] if proposed_at_submit else None),
                segment_reference_date,
                (str(entry.get("protocol") or "").strip()[:64] or None),
                (str(entry.get("ergani_submission_id") or "").strip()[:32] or None),
                (str(entry.get("submit_date") or "").strip()[:64] or None),
            ),
        )


def record_ergani_submit(
    *,
    store_id: int,
    week_from: date,
    employee_afm: str,
    work_date: date,
    submission_code: str,
    declaration_id: int | None,
    success: bool,
    protocol: str | None,
    ergani_submission_id: str | None,
    submit_date_text: str | None,
    proposed_at_submit: str | None = None,
    segment_reference_date: date | None = None,
    submitted_by: str | None = None,
) -> dict[str, Any] | None:
    if not submit_table_available():
        return None
    day_id = get_day_id(
        store_id=store_id,
        week_from=week_from,
        employee_afm=employee_afm,
        work_date=work_date,
    )
    if not day_id:
        return None
    with cursor(commit=True) as cur:
        cur.execute(f"""
            INSERT dbo.{_SUBMIT_TABLE}
                (day_id, submission_code, declaration_id, proposed_at_submit, segment_reference_date,
                 protocol, ergani_submission_id, submit_date_text, success, submitted_by)
            OUTPUT INSERTED.id,
                   CAST(INSERTED.submitted_at AS datetime2) AS submitted_at
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            int(day_id),
            str(submission_code),
            int(declaration_id) if declaration_id else None,
            (str(proposed_at_submit).strip()[:64] if proposed_at_submit else None),
            segment_reference_date,
            (str(protocol).strip()[:64] if protocol else None),
            (str(ergani_submission_id).strip()[:32] if ergani_submission_id else None),
            (str(submit_date_text).strip()[:64] if submit_date_text else None),
            1 if success else 0,
            (str(submitted_by).strip()[:128] if submitted_by else None),
        ))
        inserted = cur.fetchone()
    seg_display = segment_reference_date.strftime("%d/%m/%Y") if segment_reference_date else None
    entry = {
        "protocol": protocol,
        "ergani_submission_id": ergani_submission_id,
        "submit_date": submit_date_text,
        "submitted_at": inserted[1].isoformat(timespec="seconds") if inserted and inserted[1] else None,
        "declaration_id": declaration_id,
        "proposed_at_submit": proposed_at_submit,
        "segment_date": seg_display,
    }
    if submission_code == SUBMISSION_CODE_WTO_DAILY_A and proposed_at_submit:
        entry["matches_proposal"] = True
    if submission_code == SUBMISSION_CODE_WTO_DAILY_A:
        return {"schedule": entry}
    if submission_code == SUBMISSION_CODE_WTO_OV_A and seg_display:
        return {"overtime": {seg_display: entry}}
    return None


def _overtime_minutes_from_request_json(request_json: str | None) -> int:
    """Extract the exact submitted WTOOvA intervals from the persisted request."""
    try:
        payload = json.loads(request_json or "{}")
        analytics = payload["WTOS"]["WTO"][0]["Ergazomenoi"]["ErgazomenoiWTO"][0][
            "ErgazomenosAnalytics"
        ]["ErgazomenosWTOAnalytics"]
    except (TypeError, KeyError, IndexError, json.JSONDecodeError):
        return 0
    total = 0
    for item in analytics if isinstance(analytics, list) else []:
        try:
            start = datetime.strptime(str(item.get("f_from") or "").strip(), "%H:%M")
            end = datetime.strptime(str(item.get("f_to") or "").strip(), "%H:%M")
        except (TypeError, ValueError):
            continue
        minutes = int((end - start).total_seconds() // 60)
        if minutes < 0:
            minutes += 1440
        total += minutes
    return total


def successful_overtime_minutes_for_year(*, store_id: int, employee_afm: str, year: int) -> int:
    """Count latest successful WTOOvA submissions per day/segment for an employee."""
    with cursor() as cur:
        cur.execute("""
            WITH ranked AS (
                SELECT decl.request_json,
                       ROW_NUMBER() OVER (
                           PARTITION BY s.day_id, s.segment_reference_date
                           ORDER BY s.submitted_at DESC, s.id DESC
                       ) AS rn
                FROM dbo.karta_apologistic_submit s
                JOIN dbo.karta_apologistic_day d ON d.id = s.day_id
                LEFT JOIN dbo.karta_declaration decl ON decl.id = s.declaration_id
                WHERE d.store_id = ? AND d.employee_afm = ?
                  AND s.submission_code = ? AND s.success = 1
                  AND s.segment_reference_date >= ? AND s.segment_reference_date < ?
            )
            SELECT request_json FROM ranked WHERE rn = 1
        """, (
            int(store_id), str(employee_afm).zfill(9), SUBMISSION_CODE_WTO_OV_A,
            date(int(year), 1, 1), date(int(year) + 1, 1, 1),
        ))
        rows = cur.fetchall()
    return sum(_overtime_minutes_from_request_json(row[0]) for row in rows)


_EVENT_TYPE_ORDER = {"ergani_submit": 0, "proposal_edit": 1, "recalc": 2}


def _apologistic_activity_row(item: dict[str, Any]) -> dict[str, Any]:
    event_at = item.get("event_at")
    if hasattr(event_at, "isoformat"):
        item["event_at"] = event_at.isoformat(timespec="seconds")
    for key in ("week_from", "week_to"):
        value = item.get(key)
        if hasattr(value, "isoformat"):
            item[key] = value.isoformat()
    if item.get("employee_name"):
        item["employee_name"] = str(item["employee_name"]).strip() or None
    return item


def list_apologistic_activity(
    *,
    store_id: int | None = None,
    limit: int = 20,
    before_at: datetime | None = None,
    before_type: str | None = None,
    before_id: int | None = None,
) -> dict[str, Any]:
    """Ενοποιημένο ιστορικό επαναϋπολογισμών, χειροκίνητων προτάσεων και υποβολών Ergani."""
    if not tables_available():
        return {"rows": [], "has_more": False, "next_before": None, "limit": limit}
    limit = max(1, min(int(limit or 20), 200))
    run_store = "AND r.store_id = ?" if store_id is not None else ""
    day_store = "AND d.store_id = ?" if store_id is not None else ""
    submit_union = ""
    if submit_table_available():
        submit_union = f"""
            UNION ALL

            SELECT
                N'ergani_submit',
                s.id,
                s.submitted_at,
                0,
                d.store_id,
                st.name,
                r.week_from, r.week_to, r.calculation_version, r.status,
                NULL, NULL,
                d.employee_afm,
                LTRIM(RTRIM(CONCAT(
                    COALESCE(JSON_VALUE(d.effective_json, '$.eponymo'), N''),
                    N' ',
                    COALESCE(JSON_VALUE(d.effective_json, '$.onoma'), N'')
                ))),
                CONVERT(varchar(10), d.work_date, 103),
                NULL, NULL, NULL, s.submitted_by,
                s.submission_code, s.protocol, s.proposed_at_submit,
                CASE
                    WHEN s.segment_reference_date IS NULL THEN NULL
                    ELSE CONVERT(varchar(10), s.segment_reference_date, 103)
                END,
                s.success, s.submitted_by
            FROM dbo.karta_apologistic_submit s
            INNER JOIN dbo.karta_apologistic_day d ON d.id = s.day_id
            INNER JOIN dbo.karta_apologistic_run r ON r.id = d.run_id
            INNER JOIN dbo.karta_store_config st ON st.id = d.store_id
            WHERE s.success = 1
            {day_store}
        """

    cursor_filter = ""
    params: list[Any] = []
    if store_id is not None:
        sid = int(store_id)
        params.extend([sid, sid])
        if submit_table_available():
            params.append(sid)

    if before_at is not None and before_type and before_id is not None:
        type_rank = _EVENT_TYPE_ORDER.get(str(before_type), 99)
        cursor_filter = """
          AND (
            src.event_at < ?
            OR (src.event_at = ? AND src.type_rank > ?)
            OR (src.event_at = ? AND src.type_rank = ? AND src.event_id < ?)
          )
        """
        params.extend([before_at, before_at, type_rank, before_at, type_rank, int(before_id)])

    params.append(limit + 1)
    sql = f"""
        SELECT TOP (?)
            src.event_type, src.event_id,
            CAST(src.event_at AS datetime2) AS event_at,
            src.type_rank, src.store_id, src.store_name,
            src.week_from, src.week_to, src.calculation_version, src.run_status,
            src.day_count, src.error_summary,
            src.employee_afm, src.employee_name, src.work_date,
            src.field_name, src.old_value, src.new_value, src.changed_by,
            src.submission_code, src.protocol, src.proposed_at_submit,
            src.segment_date, src.submit_success, src.submitted_by
        FROM (
            SELECT
                N'recalc' AS event_type,
                r.id AS event_id,
                COALESCE(r.completed_at, r.updated_at) AS event_at,
                2 AS type_rank,
                r.store_id,
                st.name AS store_name,
                r.week_from, r.week_to, r.calculation_version, r.status AS run_status,
                (SELECT COUNT(*) FROM dbo.karta_apologistic_day d2 WHERE d2.run_id = r.id) AS day_count,
                r.error_summary,
                NULL AS employee_afm, NULL AS employee_name, NULL AS work_date,
                NULL AS field_name, NULL AS old_value, NULL AS new_value, NULL AS changed_by,
                NULL AS submission_code, NULL AS protocol, NULL AS proposed_at_submit,
                NULL AS segment_date, NULL AS submit_success, NULL AS submitted_by
            FROM dbo.karta_apologistic_run r
            INNER JOIN dbo.karta_store_config st ON st.id = r.store_id
            WHERE r.status <> N'running' AND COALESCE(r.completed_at, r.updated_at) IS NOT NULL
            {run_store}

            UNION ALL

            SELECT
                N'proposal_edit',
                c.id,
                c.changed_at,
                1,
                d.store_id,
                st.name,
                r.week_from, r.week_to, r.calculation_version, r.status,
                NULL, NULL,
                d.employee_afm,
                LTRIM(RTRIM(CONCAT(
                    COALESCE(JSON_VALUE(d.effective_json, '$.eponymo'), N''),
                    N' ',
                    COALESCE(JSON_VALUE(d.effective_json, '$.onoma'), N'')
                ))),
                CONVERT(varchar(10), d.work_date, 103),
                c.field_name, c.old_value, c.new_value, c.changed_by,
                NULL, NULL, NULL, NULL, NULL, NULL
            FROM dbo.karta_apologistic_change c
            INNER JOIN dbo.karta_apologistic_day d ON d.id = c.day_id
            INNER JOIN dbo.karta_apologistic_run r ON r.id = d.run_id
            INNER JOIN dbo.karta_store_config st ON st.id = d.store_id
            WHERE c.field_name = N'proposed'
            {day_store}
            {submit_union}
        ) src
        WHERE 1=1
        {cursor_filter}
        ORDER BY src.event_at DESC, src.type_rank ASC, src.event_id DESC
    """
    with cursor(commit=False) as cur:
        cur.execute(sql, tuple(params))
        raw_rows = rows_to_dicts(cur)
    rows = [_apologistic_activity_row(dict(item)) for item in raw_rows[:limit]]
    has_more = len(raw_rows) > limit
    next_before = None
    if has_more and rows:
        last = rows[-1]
        next_before = {
            "at": last.get("event_at"),
            "type": last.get("event_type"),
            "id": last.get("event_id"),
        }
    return {"rows": rows, "has_more": has_more, "next_before": next_before, "limit": limit}
