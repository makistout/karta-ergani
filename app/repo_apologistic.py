"""Persisted, editable weekly retrospective results."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from datetime import date, datetime
from typing import Any

from app.db import cursor
from app.row_util import row_to_dict, rows_to_dicts


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
            SELECT d.work_date, d.effective_json, r.week_from, r.week_to,
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
                item = json.loads(record[1])
            except (TypeError, json.JSONDecodeError):
                continue
            item["source"] = "snapshot"
            item["finalized"] = True
            item["week_from"] = record[2].isoformat()
            item["week_to"] = record[3].isoformat()
            item["run_status"] = str(record[4])
            item["calculation_version"] = str(record[5])
            item["completed_at"] = record[6].isoformat() if record[6] else None
            rows.append(item)
        return rows


def update_proposed(*, store_id: int, week_from: date, employee_afm: str,
                    work_date: date, proposed: str, changed_by: str | None) -> dict[str, Any]:
    value = str(proposed or "").strip()
    match = re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d–([01]\d|2[0-3]):[0-5]\d", value)
    if not match:
        raise ValueError("Η πρόταση πρέπει να είναι έγκυρο ωράριο σε μορφή ΩΩ:ΛΛ–ΩΩ:ΛΛ")
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
            return {"proposed": value, "changed": False}
        override["proposed"] = value
        effective["proposed"] = value
        report = json.loads(row[5])
        for item in report.get("days") or []:
            if str(item.get("employee_afm") or "") == employee_afm and str(item.get("work_date") or "") == work_date.strftime("%d/%m/%Y"):
                item["proposed"] = value
                break
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
    return {"proposed": value, "changed": True}
