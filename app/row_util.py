"""Βοηθητικά για pyodbc rows."""

from __future__ import annotations

from typing import Any

import pyodbc


def rows_to_dicts(cur: pyodbc.Cursor) -> list[dict[str, Any]]:
    if not cur.description:
        return []
    cols = [c[0] for c in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def row_to_dict(cur: pyodbc.Cursor, row: tuple) -> dict[str, Any]:
    cols = [c[0] for c in cur.description]
    return dict(zip(cols, row))
