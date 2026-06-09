"""Καταγραφή λειτουργιών karta-ergani — αρχείο logs/ + buffer ανά αίτημα."""

from __future__ import annotations

import json
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parents[1]
_LOG_DIR = _ROOT / "logs"
_LOG_FILE = _LOG_DIR / "karta-ergani.log"
_LOCK = threading.Lock()


def log_dir() -> Path:
    return _LOG_DIR


class KartaLogger:
    """Logger μίας διαδικασίας (sync, wizard, κ.λπ.) — γράφει στο αρχείο και κρατά entries."""

    def __init__(
        self,
        operation: str,
        *,
        store_id: int | None = None,
        store_name: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> None:
        self.operation = operation
        self.store_id = store_id
        self.store_name = store_name
        self._ctx = extra or {}
        self.entries: list[dict[str, Any]] = []

    def _append(self, level: str, message: str, **fields: Any) -> dict[str, Any]:
        entry: dict[str, Any] = {
            "ts": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "level": level,
            "operation": self.operation,
            "message": message,
        }
        if self.store_id is not None:
            entry["store_id"] = self.store_id
        if self.store_name:
            entry["store_name"] = self.store_name
        entry.update(self._ctx)
        entry.update({k: v for k, v in fields.items() if v is not None})
        self.entries.append(entry)

        line = (
            f"{entry['ts']} [{level}] {self.operation}"
            + (f" store={self.store_name!r}" if self.store_name else "")
            + f": {message}"
        )
        if fields:
            line += " | " + json.dumps(fields, ensure_ascii=False, default=str)
        _write_line(line)
        return entry

    def info(self, message: str, **fields: Any) -> dict[str, Any]:
        return self._append("INFO", message, **fields)

    def warning(self, message: str, **fields: Any) -> dict[str, Any]:
        return self._append("WARN", message, **fields)

    def error(self, message: str, **fields: Any) -> dict[str, Any]:
        return self._append("ERROR", message, **fields)

    def tail(self, limit: int = 50) -> list[dict[str, Any]]:
        lim = max(1, min(int(limit), 200))
        return self.entries[-lim:]


def _write_line(line: str) -> None:
    try:
        _LOG_DIR.mkdir(parents=True, exist_ok=True)
        with _LOCK:
            with _LOG_FILE.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")
    except OSError:
        pass


def logger_for_store(operation: str, ctx: dict[str, Any] | None) -> KartaLogger:
    ctx = ctx or {}
    return KartaLogger(
        operation,
        store_id=ctx.get("id"),
        store_name=ctx.get("name"),
        extra={
            "employer_afm": ctx.get("employer_afm"),
            "branch_aa": ctx.get("branch_aa"),
        },
    )
