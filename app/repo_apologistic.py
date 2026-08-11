"""Persisted, editable weekly retrospective results."""

from __future__ import annotations

import json
import re
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
        live_keys: set[tuple[str, date]] = set()
        for day in report.get("days") or []:
            work_date = datetime.strptime(str(day["work_date"]), "%d/%m/%Y").date()
            afm = str(day.get("employee_afm") or "")
            key = (afm, work_date)
            live_keys.add(key)
            override_raw, review_status = saved.get(key, (None, "draft"))
            try:
                override = json.loads(override_raw) if override_raw else None
            except (TypeError, json.JSONDecodeError):
                override = None
            effective = _merge(day, override)
            effective_days.append(effective)
            cur.execute("""
                MERGE dbo.karta_apologistic_day AS target
                USING (SELECT ? AS run_id, ? AS employee_afm, ? AS work_date) AS source
                ON target.run_id=source.run_id AND target.employee_afm=source.employee_afm AND target.work_date=source.work_date
                WHEN MATCHED THEN UPDATE SET generated_json=?, effective_json=?, generated_at=SYSDATETIMEOFFSET(), updated_at=SYSDATETIMEOFFSET()
                WHEN NOT MATCHED THEN INSERT (run_id, store_id, employee_afm, work_date, generated_json, effective_json)
                    VALUES (?, ?, ?, ?, ?, ?);
            """, (run_id, afm, work_date, _json(day), _json(effective), run_id, store_id, afm, work_date, _json(day), _json(effective)))

        for key, (_, review_status) in saved.items():
            if key not in live_keys and review_status not in ("approved", "locked"):
                cur.execute("DELETE FROM dbo.karta_apologistic_day WHERE run_id=? AND employee_afm=? AND work_date=? AND override_json IS NULL", (run_id, key[0], key[1]))

        effective_report = dict(report)
        effective_report["days"] = effective_days
        # Until field-level editing is exposed, summaries are identical; day overrides remain authoritative.
        cur.execute("""
            UPDATE dbo.karta_apologistic_run SET status=N'draft', generated_report_json=?,
                effective_report_json=?, completed_at=SYSDATETIMEOFFSET(), updated_at=SYSDATETIMEOFFSET()
            WHERE id=?
        """, (_json(report), _json(effective_report), run_id))
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
    for day in report.get("days") or []:
        day["proposal_history"] = histories.get((str(day.get("employee_afm") or ""), str(day.get("work_date") or "")), [])
    meta = {k: run.get(k) for k in ("id", "status", "calculation_version", "started_at", "completed_at", "updated_at")}
    return report, meta


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
