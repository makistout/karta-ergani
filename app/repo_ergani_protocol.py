"""Κατάλογος πρωτοκόλλων Ergani (portal WorkCardSearch) — pyodbc."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

import pyodbc

from app.db import cursor
from app.work_card_payload import norm_afm, tz_athens


def table_missing_message(exc: BaseException) -> str | None:
    if isinstance(exc, pyodbc.Error):
        err = exc.args[0] if exc.args else ""
        if err == "42S02" or "karta_ergani_protocol" in str(exc):
            return (
                "Λείπει ο πίνακας karta_ergani_protocol στη βάση. "
                "Τρέξτε sql/alter_add_karta_ergani_protocol.sql ή "
                "python scripts/ensure_karta_ergani_protocol_table.py"
            )
    return None


def parse_portal_submit_datetime(text: str) -> datetime | None:
    raw = str(text or "").strip()
    if not raw:
        return None
    for fmt in ("%d/%m/%Y %H:%M", "%d/%m/%Y %H:%M:%S"):
        try:
            dt = datetime.strptime(raw, fmt)
            return dt.replace(tzinfo=tz_athens())
        except ValueError:
            continue
    return None


def _parse_overdue(value: str | None) -> bool | None:
    text = str(value or "").strip().lower()
    if not text:
        return None
    if text in ("ναι", "yes", "1", "true"):
        return True
    if text in ("όχι", "οχι", "no", "0", "false"):
        return False
    return None


def normalize_protocol_row(
    cells: list[str],
    *,
    employer_afm: str,
    branch_aa: str,
) -> dict[str, Any] | None:
    if len(cells) < 5:
        return None
    protocol = str(cells[4] or "").strip()
    if not protocol:
        return None
    branch = str(cells[0] or "").strip() or str(branch_aa or "0").strip() or "0"
    submit_text = str(cells[3] or "").strip()
    return {
        "employer_afm": norm_afm(employer_afm),
        "branch_aa": branch[:32],
        "submission_code": "WRKCardSE",
        "protocol": protocol[:128],
        "submit_date_text": submit_text[:128] or None,
        "submit_at": parse_portal_submit_datetime(submit_text),
        "submission_status": (str(cells[1] or "").strip()[:64] or None),
        "declaration_type": (str(cells[2] or "").strip()[:256] or None),
        "overdue": _parse_overdue(cells[5] if len(cells) > 5 else None),
        "source": "portal_excel",
    }


def parse_card_protocol_export_rows(
    rows: list[list[str]],
    *,
    employer_afm: str,
    branch_aa: str,
) -> list[dict[str, Any]]:
    if not rows:
        return []
    start = 0
    header = [str(c or "").strip().lower() for c in rows[0]]
    if any("πρωτοκόλλ" in h or "protocol" in h for h in header):
        start = 1
    out: list[dict[str, Any]] = []
    for cells in rows[start:]:
        item = normalize_protocol_row(cells, employer_afm=employer_afm, branch_aa=branch_aa)
        if not item:
            continue
        dtype = str(item.get("declaration_type") or "").lower()
        if dtype and "έναρξης" not in dtype and "λήξης" not in dtype:
            continue
        out.append(item)
    return out


def upsert_protocol_rows(
    store_id: int,
    rows: list[dict[str, Any]],
    *,
    sync_run_id: str | None = None,
) -> dict[str, int]:
    if not rows:
        return {"inserted": 0, "updated": 0, "total": 0}
    inserted = 0
    updated = 0
    sid = int(store_id)
    run = (sync_run_id or "").strip()[:64] or None
    with cursor() as cur:
        for row in rows:
            protocol = str(row.get("protocol") or "").strip()
            if not protocol:
                continue
            cur.execute(
                """
                SELECT id FROM dbo.karta_ergani_protocol
                WHERE store_id = ? AND protocol = ?
                """,
                (sid, protocol),
            )
            existing = cur.fetchone()
            if existing:
                cur.execute(
                    """
                    UPDATE dbo.karta_ergani_protocol
                    SET employer_afm = ?,
                        branch_aa = ?,
                        submission_code = ?,
                        submit_at = ?,
                        submit_date_text = ?,
                        submission_status = ?,
                        declaration_type = ?,
                        overdue = ?,
                        source = ?,
                        synced_at = SYSDATETIMEOFFSET(),
                        sync_run_id = ?
                    WHERE id = ?
                    """,
                    (
                        row.get("employer_afm"),
                        row.get("branch_aa"),
                        row.get("submission_code") or "WRKCardSE",
                        row.get("submit_at"),
                        row.get("submit_date_text"),
                        row.get("submission_status"),
                        row.get("declaration_type"),
                        1 if row.get("overdue") is True else (0 if row.get("overdue") is False else None),
                        row.get("source") or "portal_excel",
                        run,
                        int(existing[0]),
                    ),
                )
                updated += 1
            else:
                cur.execute(
                    """
                    INSERT INTO dbo.karta_ergani_protocol (
                        store_id, employer_afm, branch_aa, submission_code, protocol,
                        submit_at, submit_date_text, submission_status, declaration_type,
                        overdue, source, sync_run_id
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        sid,
                        row.get("employer_afm"),
                        row.get("branch_aa"),
                        row.get("submission_code") or "WRKCardSE",
                        protocol,
                        row.get("submit_at"),
                        row.get("submit_date_text"),
                        row.get("submission_status"),
                        row.get("declaration_type"),
                        1 if row.get("overdue") is True else (0 if row.get("overdue") is False else None),
                        row.get("source") or "portal_excel",
                        run,
                    ),
                )
                inserted += 1
    return {"inserted": inserted, "updated": updated, "total": inserted + updated}


def earliest_store_activity_date(
    store_id: int,
    employer_afm: str,
    branch_aa: str,
) -> date | None:
    afm = norm_afm(employer_afm)
    aa = str(branch_aa or "0").strip()[:32] or "0"
    sid = int(store_id)
    candidates: list[date] = []
    with cursor(commit=False) as cur:
        cur.execute(
            """
            SELECT MIN(CAST(started_at AS date))
            FROM dbo.karta_sync_run
            WHERE store_id = ?
            """,
            (sid,),
        )
        row = cur.fetchone()
        if row and row[0]:
            candidates.append(row[0])

        cur.execute(
            """
            SELECT MIN(TRY_CONVERT(date, w.work_date, 103))
            FROM dbo.karta_work_log w
            WHERE w.employer_afm = ? AND w.branch_aa = ?
            """,
            (afm, aa),
        )
        row = cur.fetchone()
        if row and row[0]:
            candidates.append(row[0])

        cur.execute(
            """
            SELECT MIN(TRY_CONVERT(date, e.f_reference_date, 120))
            FROM dbo.karta_card_event e
            WHERE e.f_afm_ergodoti = ? AND e.f_aa = ?
            """,
            (afm, aa),
        )
        row = cur.fetchone()
        if row and row[0]:
            candidates.append(row[0])

    return min(candidates) if candidates else None
