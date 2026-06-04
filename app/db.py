"""Σύνδεση MSSQL μέσω pyodbc μόνο."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

import pyodbc

from config import Config


def get_connection() -> pyodbc.Connection:
    return pyodbc.connect(Config.pyodbc_connection_string(), autocommit=False)


@contextmanager
def cursor(commit: bool = True) -> Iterator[pyodbc.Cursor]:
    conn = get_connection()
    cur = conn.cursor()
    try:
        yield cur
        if commit:
            conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()


@contextmanager
def connection() -> Iterator[pyodbc.Connection]:
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
