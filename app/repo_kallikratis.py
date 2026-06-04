"""Αναζήτηση Καλλικράτη — ανάγνωση από CATALOG_DATABASE (π.χ. ergani_ii)."""

from __future__ import annotations

import re
from typing import Any

from app.db import cursor
from app.row_util import rows_to_dicts
from config import Config


def _catalog_db() -> str:
    return (Config.CATALOG_DATABASE or "ergani_ii").replace("]", "]]")


def search_kallikratis(query: str, limit: int = 20) -> list[dict[str, Any]]:
    q = (query or "").strip()
    if len(q) < 2:
        return []
    lim = max(1, min(int(limit), 50))
    db = _catalog_db()
    digits = re.sub(r"\D", "", q)
    try:
        with cursor(commit=False) as cur:
            if digits and len(digits) <= 8:
                cur.execute(
                    f"""
                    SELECT TOP ({lim}) code, name_local, municipality_name, kind
                    FROM [{db}].dbo.ergani_kallikratis_catalog
                    WHERE code LIKE ? + '%'
                    ORDER BY code
                    """,
                    (digits[:8],),
                )
            else:
                like = "%" + q.replace("%", "").replace("_", "") + "%"
                cur.execute(
                    f"""
                    SELECT TOP ({lim}) code, name_local, municipality_name, kind
                    FROM [{db}].dbo.ergani_kallikratis_catalog
                    WHERE search_text LIKE ?
                    ORDER BY code
                    """,
                    (like,),
                )
            rows = rows_to_dicts(cur)
    except Exception:
        return []
    for r in rows:
        code = r.get("code", "")
        loc = r.get("name_local") or ""
        mun = r.get("municipality_name") or ""
        r["label"] = f"{code} — {loc}" + (f" ({mun})" if mun else "")
    return rows
