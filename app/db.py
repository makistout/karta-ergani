"""Σύνδεση MSSQL μέσω pyodbc — queue pool (reuse μεταξύ Flask requests)."""

from __future__ import annotations

from contextlib import contextmanager
from queue import Empty, Full, Queue
from typing import Iterator

import pyodbc

from config import Config

_POOL_SIZE = 8
_pool: Queue[pyodbc.Connection] = Queue(maxsize=_POOL_SIZE)


def _new_connection() -> pyodbc.Connection:
    return pyodbc.connect(Config.pyodbc_connection_string(), autocommit=False)


def _discard_connection(conn: pyodbc.Connection | None) -> None:
    if conn is None:
        return
    try:
        conn.close()
    except pyodbc.Error:
        pass


def _connection_alive(conn: pyodbc.Connection) -> bool:
    try:
        conn.cursor().execute("SELECT 1")
        return True
    except pyodbc.Error:
        return False


def get_connection() -> pyodbc.Connection:
    while True:
        try:
            conn = _pool.get_nowait()
        except Empty:
            break
        if _connection_alive(conn):
            return conn
        _discard_connection(conn)
    return _new_connection()


def release_connection(conn: pyodbc.Connection, *, discard: bool = False) -> None:
    if discard:
        _discard_connection(conn)
        return
    try:
        _pool.put_nowait(conn)
    except Full:
        _discard_connection(conn)


@contextmanager
def cursor(commit: bool = True) -> Iterator[pyodbc.Cursor]:
    conn = get_connection()
    cur = conn.cursor()
    discard = False
    try:
        yield cur
        if commit:
            conn.commit()
    except pyodbc.Error:
        try:
            conn.rollback()
        except pyodbc.Error:
            pass
        discard = True
        raise
    except Exception:
        try:
            conn.rollback()
        except pyodbc.Error:
            pass
        raise
    finally:
        cur.close()
        release_connection(conn, discard=discard)


@contextmanager
def connection() -> Iterator[pyodbc.Connection]:
    conn = get_connection()
    discard = False
    try:
        yield conn
        conn.commit()
    except pyodbc.Error:
        try:
            conn.rollback()
        except pyodbc.Error:
            pass
        discard = True
        raise
    except Exception:
        try:
            conn.rollback()
        except pyodbc.Error:
            pass
        raise
    finally:
        release_connection(conn, discard=discard)
