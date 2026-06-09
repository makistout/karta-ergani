"""Καταγραφή λειτουργιών karta-ergani — βάση MSSQL + buffer ανά αίτημα."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from app import repo_sync_log


class KartaLogger:
    """Logger μίας διαδικασίας (sync, wizard, κ.λπ.) — γράφει στη βάση και κρατά entries."""

    def __init__(
        self,
        operation: str,
        *,
        store_id: int | None = None,
        store_name: str | None = None,
        run_id: str | None = None,
        extra: dict[str, Any] | None = None,
        register_run: bool = True,
    ) -> None:
        self.operation = operation
        self.store_id = store_id
        self.store_name = store_name
        self.run_id = run_id or str(uuid.uuid4())
        self._ctx = extra or {}
        self.entries: list[dict[str, Any]] = []
        self._seq = 0
        self._run_registered = False
        if register_run:
            self._ensure_run()

    def _ensure_run(self) -> None:
        if self._run_registered:
            return
        repo_sync_log.create_run(
            self.run_id,
            operation=self.operation,
            store_id=self.store_id,
        )
        self._run_registered = True

    def _append(self, level: str, message: str, **fields: Any) -> dict[str, Any]:
        self._ensure_run()
        self._seq += 1
        entry: dict[str, Any] = {
            "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "level": level,
            "operation": self.operation,
            "message": message,
            "seq": self._seq,
        }
        if self.store_id is not None:
            entry["store_id"] = self.store_id
        if self.store_name:
            entry["store_name"] = self.store_name
        entry.update(self._ctx)
        extra_fields = {k: v for k, v in fields.items() if v is not None}
        entry.update(extra_fields)
        self.entries.append(entry)

        persist_fields = dict(extra_fields)
        if self.store_id is not None:
            persist_fields.setdefault("store_id", self.store_id)
        if self.store_name:
            persist_fields.setdefault("store_name", self.store_name)
        repo_sync_log.append_line(
            self.run_id,
            self._seq,
            level,
            message,
            persist_fields or None,
        )
        return entry

    def info(self, message: str, **fields: Any) -> dict[str, Any]:
        return self._append("INFO", message, **fields)

    def warning(self, message: str, **fields: Any) -> dict[str, Any]:
        return self._append("WARN", message, **fields)

    def error(self, message: str, **fields: Any) -> dict[str, Any]:
        return self._append("ERROR", message, **fields)

    def tail(self, limit: int = 50) -> list[dict[str, Any]]:
        lim = max(1, min(int(limit), 200))
        db_lines = repo_sync_log.list_lines(self.run_id, limit=lim)
        if db_lines:
            return db_lines
        return self.entries[-lim:]


def logger_for_store(
    operation: str,
    ctx: dict[str, Any] | None,
    *,
    run_id: str | None = None,
    register_run: bool = True,
) -> KartaLogger:
    ctx = ctx or {}
    return KartaLogger(
        operation,
        store_id=ctx.get("id"),
        store_name=ctx.get("name"),
        run_id=run_id,
        register_run=register_run and run_id is None,
        extra={
            "employer_afm": ctx.get("employer_afm"),
            "branch_aa": ctx.get("branch_aa"),
        },
    )
