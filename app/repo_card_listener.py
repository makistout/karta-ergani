"""Database access for the isolated WRKCardSE listener channel."""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import datetime, timezone
from typing import Any

from app.db import cursor
from app.row_util import row_to_dict


def _secret_hash(secret: str) -> bytes:
    return hashlib.sha256(secret.encode("utf-8")).digest()


def listener_tables_available() -> bool:
    try:
        with cursor(commit=False) as cur:
            cur.execute("SELECT OBJECT_ID(N'dbo.karta_card_listener_device', N'U')")
            row = cur.fetchone()
            return bool(row and row[0])
    except Exception:
        return False


def get_listener_settings(store_id: int) -> dict[str, Any]:
    with cursor(commit=False) as cur:
        cur.execute(
            """
            SELECT id, card_submission_mode, listener_offline_seconds
            FROM dbo.karta_store_config WHERE id = ?
            """,
            (int(store_id),),
        )
        row = cur.fetchone()
        if not row:
            raise ValueError(f"Store id={store_id} not found")
        data = row_to_dict(cur, row)
        if listener_tables_available():
            cur.execute(
                """
                SELECT TOP (1) device_id, device_name, agent_version, enabled,
                       CONVERT(nvarchar(40), paired_at, 127) AS paired_at,
                       CONVERT(nvarchar(40), last_seen_at, 127) AS last_seen_at,
                       last_seen_ip,
                       CONVERT(nvarchar(40), revoked_at, 127) AS revoked_at,
                       CASE WHEN enabled = 1 AND revoked_at IS NULL
                                  AND last_seen_at >= DATEADD(second, -?, SYSDATETIMEOFFSET())
                            THEN 1 ELSE 0 END AS is_online
                FROM dbo.karta_card_listener_device
                WHERE store_id = ? AND enabled = 1 AND revoked_at IS NULL
                ORDER BY paired_at DESC
                """,
                (int(data.get("listener_offline_seconds") or 60), int(store_id)),
            )
            device = cur.fetchone()
            data["device"] = row_to_dict(cur, device) if device else None
        else:
            data["device"] = None
    data["card_submission_mode"] = str(data.get("card_submission_mode") or "erganios")
    data["listener_offline_seconds"] = int(data.get("listener_offline_seconds") or 60)
    return data


def save_listener_settings(store_id: int, mode: str, offline_seconds: int) -> dict[str, Any]:
    normalized_mode = str(mode or "erganios").strip().lower()
    if normalized_mode not in {"erganios", "listener"}:
        raise ValueError("card_submission_mode must be erganios or listener")
    seconds = int(offline_seconds)
    if seconds < 15 or seconds > 600:
        raise ValueError("listener_offline_seconds must be between 15 and 600")
    with cursor() as cur:
        cur.execute(
            """
            UPDATE dbo.karta_store_config
            SET card_submission_mode = ?, listener_offline_seconds = ?,
                updated_at = SYSDATETIMEOFFSET()
            WHERE id = ?
            """,
            (normalized_mode, seconds, int(store_id)),
        )
        if cur.rowcount == 0:
            raise ValueError(f"Store id={store_id} not found")
    return get_listener_settings(store_id)


def pair_device(store_id: int, device_name: str | None = None) -> dict[str, str]:
    """Create a per-store credential. The clear token is returned exactly once."""
    token = secrets.token_urlsafe(32)
    device_id = str(uuid.uuid4())
    with cursor() as cur:
        cur.execute(
            """
            UPDATE dbo.karta_card_listener_device
            SET enabled = 0, revoked_at = SYSDATETIMEOFFSET()
            WHERE store_id = ? AND enabled = 1 AND revoked_at IS NULL;

            INSERT dbo.karta_card_listener_device
                (store_id, device_id, device_name, credential_hash)
            VALUES (?, ?, ?, ?)
            """,
            (int(store_id), int(store_id), device_id, (device_name or "")[:200] or None, _secret_hash(token)),
        )
    return {"device_id": device_id, "device_token": token}


def revoke_device(store_id: int) -> bool:
    with cursor() as cur:
        cur.execute(
            """
            UPDATE dbo.karta_card_listener_device
            SET enabled = 0, revoked_at = SYSDATETIMEOFFSET()
            WHERE store_id = ? AND enabled = 1 AND revoked_at IS NULL
            """,
            (int(store_id),),
        )
        return bool(cur.rowcount)


def authenticate_device(device_id: str, token: str, *, version: str | None = None) -> dict[str, Any] | None:
    try:
        parsed_id = str(uuid.UUID(str(device_id)))
    except (ValueError, TypeError):
        return None
    with cursor() as cur:
        cur.execute(
            """
            SELECT TOP (1) id, store_id, device_id, credential_hash, last_seen_ip
            FROM dbo.karta_card_listener_device
            WHERE device_id = ? AND enabled = 1 AND revoked_at IS NULL
            """,
            (parsed_id,),
        )
        row = cur.fetchone()
        if not row:
            return None
        data = row_to_dict(cur, row)
        expected = bytes(data.pop("credential_hash"))
        if not secrets.compare_digest(expected, _secret_hash(token or "")):
            return None
        cur.execute(
            """
            UPDATE dbo.karta_card_listener_device
            SET last_seen_at = SYSDATETIMEOFFSET(), agent_version = COALESCE(?, agent_version)
            WHERE id = ?
            """,
            ((version or "")[:32] or None, int(data["id"])),
        )
        return data


def update_device_public_ip(device_row_id: int, public_ip: str | None) -> None:
    with cursor() as cur:
        cur.execute(
            """
            UPDATE dbo.karta_card_listener_device
            SET last_seen_ip = ?, last_seen_at = SYSDATETIMEOFFSET()
            WHERE id = ? AND enabled = 1 AND revoked_at IS NULL
            """,
            ((public_ip or "")[:45] or None, int(device_row_id)),
        )


def lease_next_job(store_id: int, device_id: str, lease_seconds: int = 45) -> dict[str, Any] | None:
    with cursor() as cur:
        cur.execute(
            """
            ;WITH next_job AS (
                SELECT TOP (1) *
                FROM dbo.karta_card_listener_job WITH (UPDLOCK, READPAST, ROWLOCK)
                WHERE store_id = ? AND status = N'queued'
                  AND available_at <= SYSDATETIMEOFFSET()
                  AND fallback_deadline > SYSDATETIMEOFFSET()
                ORDER BY created_at, id
            )
            UPDATE next_job
            SET status = N'leased', device_id = ?, leased_at = SYSDATETIMEOFFSET(),
                lease_expires_at = DATEADD(second, ?, SYSDATETIMEOFFSET()),
                attempt_count = attempt_count + 1, updated_at = SYSDATETIMEOFFSET()
            OUTPUT inserted.id, inserted.job_uuid, inserted.store_id, inserted.payload_json,
                   inserted.ergani_api_base_url,
                   CONVERT(nvarchar(40), inserted.fallback_deadline, 127) AS fallback_deadline,
                   inserted.attempt_count;
            """,
            (int(store_id), str(device_id), int(lease_seconds)),
        )
        row = cur.fetchone()
        if not row:
            return None
        job = row_to_dict(cur, row)
        cur.execute(
            """
            INSERT dbo.karta_card_listener_attempt
                (job_id, device_id, execution_source, attempt_number)
            VALUES (?, ?, N'listener', ?)
            """,
            (int(job["id"]), str(device_id), int(job["attempt_count"])),
        )
        return job


def finish_job(store_id: int, device_id: str, job_uuid: str, result: dict[str, Any], *, submission_ip: str | None = None) -> bool:
    success = bool(result.get("success"))
    status = "succeeded" if success else str(result.get("status") or "failed")
    if status not in {"succeeded", "failed", "needs_review"}:
        status = "failed"
    import json

    with cursor() as cur:
        cur.execute(
            """
            UPDATE dbo.karta_card_listener_job
            SET status = ?, completed_at = SYSDATETIMEOFFSET(), updated_at = SYSDATETIMEOFFSET(),
                upstream_http_status = ?, protocol = ?, ergani_submission_id = ?,
                submit_date_text = ?, result_json = ?, error_code = ?, error_summary = ?
                , submission_ip = ?, executor_instance = ?
            OUTPUT inserted.id, inserted.attempt_count
            WHERE job_uuid = ? AND store_id = ? AND device_id = ?
              AND status IN (N'leased', N'submitting')
            """,
            (
                status,
                result.get("http_status"),
                (str(result.get("protocol") or "")[:128] or None),
                (str(result.get("ergani_submission_id") or "")[:64] or None),
                (str(result.get("submit_date") or "")[:128] or None),
                json.dumps(result.get("data"), ensure_ascii=False) if result.get("data") is not None else None,
                (str(result.get("error_code") or "")[:64] or None),
                (str(result.get("error") or "")[:1000] or None),
                (submission_ip or "")[:45] or None,
                str(device_id)[:200],
                str(job_uuid), int(store_id), str(device_id),
            ),
        )
        row = cur.fetchone()
        if not row:
            cur.execute(
                """
                SELECT status FROM dbo.karta_card_listener_job
                WHERE job_uuid = ? AND store_id = ? AND device_id = ?
                """,
                (str(job_uuid), int(store_id), str(device_id)),
            )
            existing = cur.fetchone()
            return bool(existing and str(existing[0]) in {"succeeded", "failed", "needs_review"})
        job_id, attempt_number = int(row[0]), int(row[1])
        cur.execute(
            """
            UPDATE dbo.karta_card_listener_attempt
            SET finished_at = SYSDATETIMEOFFSET(), http_status = ?, success = ?,
                error_code = ?, error_summary = ?, submission_ip = ?, executor_instance = ?
            WHERE job_id = ? AND execution_source = N'listener' AND attempt_number = ?
            """,
            (result.get("http_status"), 1 if success else 0,
             (str(result.get("error_code") or "")[:64] or None),
             (str(result.get("error") or "")[:1000] or None),
             (submission_ip or "")[:45] or None, str(device_id)[:200], job_id, attempt_number),
        )
    return True
