"""Τοπικός κατάλογος ειδικοτήτων ΣΤΕΠ'92 (Ergani EX_BASE_03 / Step92)."""

from __future__ import annotations

import re
from typing import Any

from app.db import cursor
from app.row_util import rows_to_dicts

TABLE = "karta_specialty_catalog"

ENSURE_DDL = f"""
IF OBJECT_ID(N'dbo.{TABLE}', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.{TABLE} (
        code NVARCHAR(16) NOT NULL CONSTRAINT PK_{TABLE} PRIMARY KEY CLUSTERED,
        description NVARCHAR(500) NOT NULL,
        search_text NVARCHAR(600) NOT NULL,
        synced_at DATETIMEOFFSET(7) NOT NULL
            CONSTRAINT DF_{TABLE}_synced DEFAULT (SYSDATETIMEOFFSET())
    );
    CREATE INDEX IX_{TABLE}_search ON dbo.{TABLE} (search_text);
END
"""


def ensure_table() -> None:
    with cursor() as cur:
        cur.execute(ENSURE_DDL)


def table_available() -> bool:
    try:
        with cursor(commit=False) as cur:
            cur.execute(
                """
                SELECT 1 FROM INFORMATION_SCHEMA.TABLES
                WHERE TABLE_SCHEMA = N'dbo' AND TABLE_NAME = ?
                """,
                (TABLE,),
            )
            return cur.fetchone() is not None
    except Exception:
        return False


def count_rows() -> int:
    if not table_available():
        return 0
    with cursor(commit=False) as cur:
        cur.execute(f"SELECT COUNT(*) FROM dbo.{TABLE}")
        row = cur.fetchone()
        return int(row[0] or 0) if row else 0


def last_synced_at() -> str | None:
    if not table_available():
        return None
    with cursor(commit=False) as cur:
        cur.execute(
            f"SELECT CONVERT(varchar(33), MAX(synced_at), 127) FROM dbo.{TABLE}"
        )
        row = cur.fetchone()
        if not row or row[0] is None:
            return None
        return str(row[0])


def _search_blob(code: str, description: str) -> str:
    return f"{code} {description}".casefold()


def replace_all(items: list[dict[str, str]]) -> int:
    """Αντικαθιστά ολόκληρο τον κατάλογο με τα νέα items (value/description)."""
    ensure_table()
    cleaned: list[tuple[str, str, str]] = []
    seen: set[str] = set()
    for raw in items:
        code = str(raw.get("value") or raw.get("code") or "").strip()
        desc = str(raw.get("description") or raw.get("label") or "").strip()
        if not code or code in seen:
            continue
        seen.add(code)
        cleaned.append((code[:16], desc[:500] or code, _search_blob(code, desc)[:600]))

    with cursor() as cur:
        cur.execute(f"DELETE FROM dbo.{TABLE}")
        if cleaned:
            cur.fast_executemany = True
            cur.executemany(
                f"""
                INSERT INTO dbo.{TABLE} (code, description, search_text, synced_at)
                VALUES (?, ?, ?, SYSDATETIMEOFFSET())
                """,
                cleaned,
            )
    return len(cleaned)


def search_specialties(query: str, limit: int = 40) -> list[dict[str, str]]:
    """Αναζήτηση τοπικού καταλόγου για autocomplete (κωδικός ή περιγραφή)."""
    if not table_available():
        return []
    q = (query or "").strip()
    lim = max(1, min(int(limit), 80))
    digits = re.sub(r"\D", "", q)

    with cursor(commit=False) as cur:
        if not q:
            cur.execute(
                f"""
                SELECT TOP ({lim}) code, description
                FROM dbo.{TABLE}
                ORDER BY code
                """
            )
        elif digits and (not q or q == digits or len(digits) >= 2):
            cur.execute(
                f"""
                SELECT TOP ({lim}) code, description
                FROM dbo.{TABLE}
                WHERE code LIKE ? + N'%'
                   OR search_text LIKE N'%' + ? + N'%'
                ORDER BY
                    CASE WHEN code LIKE ? + N'%' THEN 0 ELSE 1 END,
                    code
                """,
                (digits[:16], q.casefold()[:200], digits[:16]),
            )
        else:
            like = "%" + q.casefold().replace("%", "").replace("_", "") + "%"
            cur.execute(
                f"""
                SELECT TOP ({lim}) code, description
                FROM dbo.{TABLE}
                WHERE search_text LIKE ?
                ORDER BY code
                """,
                (like[:220],),
            )
        rows = rows_to_dicts(cur)

    out: list[dict[str, str]] = []
    for row in rows:
        code = str(row.get("code") or "")
        desc = str(row.get("description") or "")
        out.append({
            "value": code,
            "code": code,
            "description": desc,
            "label": f"{code} — {desc}" if desc else code,
        })
    return out


def get_by_code(code: str) -> dict[str, str] | None:
    code = str(code or "").strip()
    if not code or not table_available():
        return None
    with cursor(commit=False) as cur:
        cur.execute(
            f"SELECT TOP (1) code, description FROM dbo.{TABLE} WHERE code = ?",
            (code,),
        )
        rows = rows_to_dicts(cur)
    if not rows:
        return None
    row = rows[0]
    c = str(row.get("code") or "")
    d = str(row.get("description") or "")
    return {"value": c, "code": c, "description": d, "label": f"{c} — {d}" if d else c}


def find_by_description(text: str) -> dict[str, str] | None:
    text = str(text or "").strip()
    if not text or not table_available():
        return None
    with cursor(commit=False) as cur:
        cur.execute(
            f"""
            SELECT TOP (1) code, description
            FROM dbo.{TABLE}
            WHERE description = ? OR search_text LIKE ?
            ORDER BY CASE WHEN description = ? THEN 0 ELSE 1 END, code
            """,
            (text, "%" + text.casefold()[:200] + "%", text),
        )
        rows = rows_to_dicts(cur)
    if not rows:
        return None
    row = rows[0]
    c = str(row.get("code") or "")
    d = str(row.get("description") or "")
    return {"value": c, "code": c, "description": d, "label": f"{c} — {d}" if d else c}
