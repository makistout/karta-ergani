"""Ενδιάμεσοι πίνακες εισαγωγής εβδομαδιαίου ωραρίου από Excel."""

from __future__ import annotations

import json
from typing import Any

from app.db import cursor
from app.row_util import rows_to_dicts
from app.schedule_excel_import import format_snapshot_label, summarize_import_rows


def schedule_import_table_missing_message(exc: BaseException) -> str | None:
    text = str(exc)
    if "karta_schedule_import_batch" in text or "karta_schedule_import_row" in text:
        return (
            "Λείπουν οι πίνακες εισαγωγής ωραρίου. "
            "Τρέξτε το sql/alter_add_schedule_import_staging.sql στο SSMS."
        )
    return None


def create_import_batch(
    *,
    store_id: int,
    employer_afm: str,
    branch_aa: str,
    original_filename: str | None,
    week_label: str | None,
    created_by_user_id: int | None,
    summary: dict[str, Any],
) -> int:
    with cursor() as cur:
        cur.execute(
            """
            INSERT INTO dbo.karta_schedule_import_batch (
                store_id, employer_afm, branch_aa, original_filename,
                week_label, status, created_by_user_id, summary_json
            )
            OUTPUT INSERTED.id
            VALUES (?, ?, ?, ?, ?, N'preview', ?, ?)
            """,
            (
                int(store_id),
                str(employer_afm or "").strip()[:9],
                str(branch_aa or "0").strip()[:32] or "0",
                (original_filename or "").strip()[:255] or None,
                (week_label or "").strip()[:128] or None,
                created_by_user_id,
                json.dumps(summary, ensure_ascii=False),
            ),
        )
        row = cur.fetchone()
        return int(row[0])


def insert_import_rows(batch_id: int, rows: list[dict[str, Any]]) -> int:
    if not rows:
        return 0
    with cursor() as cur:
        n = 0
        for row in rows:
            cur.execute(
                """
                INSERT INTO dbo.karta_schedule_import_row (
                    batch_id, row_no, sheet_name, work_date, employee_afm,
                    eponymo, onoma, import_action, hour_from_1, hour_to_1,
                    hour_from_2, hour_to_2, schedule_type, change_kind,
                    current_snapshot_json, proposed_snapshot_json,
                    validation_errors_json, apply_status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    int(batch_id),
                    int(row.get("row_no") or 0),
                    (row.get("sheet_name") or "")[:64] or None,
                    str(row.get("work_date") or "").strip()[:32],
                    str(row.get("employee_afm") or "").strip()[:9],
                    (row.get("eponymo") or "")[:128] or None,
                    (row.get("onoma") or "")[:128] or None,
                    str(row.get("import_action") or "")[:16],
                    (row.get("hour_from_1") or "")[:16] or None,
                    (row.get("hour_to_1") or "")[:16] or None,
                    (row.get("hour_from_2") or "")[:16] or None,
                    (row.get("hour_to_2") or "")[:16] or None,
                    (row.get("schedule_type") or "")[:16] or None,
                    str(row.get("change_kind") or "")[:16],
                    json.dumps(row.get("current_snapshot") or [], ensure_ascii=False),
                    json.dumps(row.get("proposed_snapshot") or [], ensure_ascii=False),
                    json.dumps(row.get("validation_errors") or [], ensure_ascii=False),
                    "pending" if row.get("change_kind") in ("new", "update") and not row.get("validation_errors") else None,
                ),
            )
            n += 1
        return n


def get_import_batch(batch_id: int, *, store_id: int | None = None) -> dict[str, Any] | None:
    with cursor(commit=False) as cur:
        if store_id is not None:
            cur.execute(
                """
                SELECT id, store_id, employer_afm, branch_aa, original_filename,
                       week_label, status,
                       CAST(created_at AS datetime2) AS created_at,
                       CAST(applied_at AS datetime2) AS applied_at,
                       summary_json
                FROM dbo.karta_schedule_import_batch
                WHERE id = ? AND store_id = ?
                """,
                (int(batch_id), int(store_id)),
            )
        else:
            cur.execute(
                """
                SELECT id, store_id, employer_afm, branch_aa, original_filename,
                       week_label, status,
                       CAST(created_at AS datetime2) AS created_at,
                       CAST(applied_at AS datetime2) AS applied_at,
                       summary_json
                FROM dbo.karta_schedule_import_batch
                WHERE id = ?
                """,
                (int(batch_id),),
            )
        rows = rows_to_dicts(cur)
        return rows[0] if rows else None


def list_import_rows(batch_id: int) -> list[dict[str, Any]]:
    with cursor(commit=False) as cur:
        cur.execute(
            """
            SELECT id, batch_id, row_no, sheet_name, work_date, employee_afm,
                   eponymo, onoma, import_action, hour_from_1, hour_to_1,
                   hour_from_2, hour_to_2, schedule_type, change_kind,
                   current_snapshot_json, proposed_snapshot_json,
                   validation_errors_json, apply_status, apply_message,
                   ergani_protocol
            FROM dbo.karta_schedule_import_row
            WHERE batch_id = ?
            ORDER BY work_date, eponymo, onoma, employee_afm, row_no
            """,
            (int(batch_id),),
        )
        rows = rows_to_dicts(cur)
    for row in rows:
        for key in ("current_snapshot_json", "proposed_snapshot_json", "validation_errors_json"):
            raw = row.pop(key, None)
            try:
                row[key.replace("_json", "")] = json.loads(raw) if raw else []
            except json.JSONDecodeError:
                row[key.replace("_json", "")] = []
        row["current_label"] = format_snapshot_label(row.get("current_snapshot") or [])
        row["proposed_label"] = format_snapshot_label(row.get("proposed_snapshot") or [])
    return rows


def preview_import_batch(batch_id: int, *, store_id: int) -> dict[str, Any] | None:
    batch = get_import_batch(batch_id, store_id=store_id)
    if not batch:
        return None
    rows = list_import_rows(batch_id)
    summary = summarize_import_rows(
        [
            {
                "change_kind": row.get("change_kind"),
                "validation_errors": row.get("validation_errors") or [],
            }
            for row in rows
        ]
    )
    if batch.get("created_at") is not None:
        batch["created_at"] = str(batch["created_at"])[:19]
    if batch.get("applied_at") is not None:
        batch["applied_at"] = str(batch["applied_at"])[:19]
    try:
        batch["summary"] = json.loads(batch.pop("summary_json") or "{}")
    except json.JSONDecodeError:
        batch["summary"] = summary
    batch["summary"] = summary
    return {
        "batch": batch,
        "rows": rows,
        "summary": summary,
    }


def update_batch_status(batch_id: int, status: str, *, summary: dict[str, Any] | None = None) -> None:
    with cursor() as cur:
        if summary is not None:
            cur.execute(
                """
                UPDATE dbo.karta_schedule_import_batch
                SET status = ?, summary_json = ?,
                    applied_at = CASE WHEN ? = N'applied' THEN SYSDATETIMEOFFSET() ELSE applied_at END
                WHERE id = ?
                """,
                (status[:32], json.dumps(summary, ensure_ascii=False), status, int(batch_id)),
            )
        else:
            cur.execute(
                """
                UPDATE dbo.karta_schedule_import_batch
                SET status = ?,
                    applied_at = CASE WHEN ? = N'applied' THEN SYSDATETIMEOFFSET() ELSE applied_at END
                WHERE id = ?
                """,
                (status[:32], status, int(batch_id)),
            )


def update_import_row_result(
    row_id: int,
    *,
    apply_status: str,
    apply_message: str | None = None,
    ergani_protocol: str | None = None,
) -> None:
    with cursor() as cur:
        cur.execute(
            """
            UPDATE dbo.karta_schedule_import_row
            SET apply_status = ?, apply_message = ?, ergani_protocol = ?
            WHERE id = ?
            """,
            (
                apply_status[:16],
                (apply_message or "")[:500] or None,
                (ergani_protocol or "")[:64] or None,
                int(row_id),
            ),
        )


def list_apply_rows(batch_id: int) -> list[dict[str, Any]]:
    rows = list_import_rows(batch_id)
    return [
        row
        for row in rows
        if row.get("change_kind") in ("new", "update")
        and not (row.get("validation_errors") or [])
    ]
