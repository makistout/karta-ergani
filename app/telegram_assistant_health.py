"""Τακτικός έλεγχος ότι το telegram_assistant_service.py φορτώνει και δεν σκάει."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SERVICE_PATH = Path(__file__).with_name("telegram_assistant_service.py")
_CACHE_TTL_SEC = 15.0
_CRASH_WINDOW_HOURS = 6
_cache: dict[str, Any] = {"at": 0.0, "result": None}


def check_source(path: Path | None = None) -> dict[str, Any]:
    target = path or SERVICE_PATH
    try:
        source = target.read_text(encoding="utf-8")
        compile(source, str(target), "exec")
    except SyntaxError as exc:
        return {
            "ok": False,
            "error": f"{exc.__class__.__name__}: {exc.msg} (γραμμή {exc.lineno})",
        }
    except OSError as exc:
        return {"ok": False, "error": f"Δεν διαβάστηκε το αρχείο: {exc}"}
    return {"ok": True, "error": None}


def recent_inbound_crash(*, hours: int = _CRASH_WINDOW_HOURS) -> dict[str, Any] | None:
    try:
        from app.db import cursor
        from app.row_util import rows_to_dicts

        with cursor(commit=False) as cur:
            cur.execute(
                """
                SELECT TOP 1
                  id,
                  LEFT(error_message, 240) AS error_message,
                  CONVERT(varchar(33), received_at, 126) AS received_at,
                  LEFT(message_text, 80) AS msg
                FROM dbo.karta_telegram_inbound_message
                WHERE received_at >= DATEADD(hour, -?, SYSUTCDATETIME())
                  AND LTRIM(RTRIM(ISNULL(error_message, N''))) <> N''
                  AND (
                    LOWER(error_message) LIKE N'%indentationerror%'
                    OR LOWER(error_message) LIKE N'%syntaxerror%'
                    OR error_message LIKE N'%expected an indented block%'
                    OR error_message LIKE N'%telegram_assistant_service.py%'
                  )
                ORDER BY received_at DESC
                """,
                (int(hours),)
            )
            rows = rows_to_dicts(cur)
    except Exception:
        return None
    return rows[0] if rows else None


def _stamp(value: Any) -> str:
    return str(value or "").strip()


def crash_is_newer(crash: dict[str, Any] | None, last_ok: dict[str, Any] | None) -> bool:
    """Προσοχή μόνο αν το crash έγινε μετά την τελευταία επιτυχημένη εντολή."""
    if not crash:
        return False
    crash_at = _stamp(crash.get("received_at"))
    if not crash_at:
        return True
    ok_at = _stamp((last_ok or {}).get("created_at"))
    if not ok_at:
        return True
    return crash_at > ok_at


def last_successful_task() -> dict[str, Any] | None:
    try:
        from app.db import cursor
        from app.row_util import rows_to_dicts

        with cursor(commit=False) as cur:
            cur.execute(
                """
                SELECT TOP 1
                  id,
                  intent,
                  task_status,
                  CONVERT(varchar(33), created_at, 126) AS created_at
                FROM dbo.karta_assistant_task
                WHERE task_status IN (N'completed', N'answered')
                ORDER BY created_at DESC
                """
            )
            rows = rows_to_dicts(cur)
    except Exception:
        return None
    return rows[0] if rows else None


def assistant_health(*, use_cache: bool = True) -> dict[str, Any]:
    now = time.monotonic()
    if use_cache and _cache["result"] is not None and (now - float(_cache["at"])) < _CACHE_TTL_SEC:
        return _cache["result"]

    try:
        source = check_source()
        crash = recent_inbound_crash() if source.get("ok") else None
        last_ok = last_successful_task()
        if not source.get("ok"):
            status = "error"
            label = "AI Agent σφάλμα"
            detail = str(source.get("error") or "Το telegram_assistant_service.py δεν φορτώνει.")
        elif crash_is_newer(crash, last_ok):
            status = "warn"
            label = "AI Agent προσοχή"
            detail = str(crash.get("error_message") or "Πρόσφατο σφάλμα σε εντολή Telegram.")
        else:
            status = "ok"
            label = "AI Agent"
            detail = "Το telegram_assistant_service.py φορτώνει κανονικά."
        result = {
            "ok": status == "ok",
            "status": status,
            "label": label,
            "detail": detail,
            "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "source": source,
            "last_crash": crash,
            "last_ok": last_ok,
        }
    except Exception as exc:
        result = {
            "ok": False,
            "status": "error",
            "label": "AI Agent σφάλμα",
            "detail": str(exc)[:240],
            "checked_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "source": {"ok": False, "error": str(exc)[:240]},
            "last_crash": None,
            "last_ok": None,
        }
    _cache["at"] = now
    _cache["result"] = result
    return result
