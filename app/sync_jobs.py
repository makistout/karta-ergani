"""Background portal sync jobs — live progress μέσω polling."""

from __future__ import annotations

import copy
import threading
import uuid
from collections.abc import Iterator
from typing import Any, Callable

_jobs: dict[str, dict[str, Any]] = {}
_lock = threading.Lock()


def _apply_event(job: dict[str, Any], ev: dict[str, Any]) -> None:
    event = ev.get("event")
    if event == "progress":
        job["message"] = ev.get("message") or job.get("message")
        job["step"] = ev.get("step", job.get("step", 0))
        job["total"] = ev.get("total", job.get("total", 0))
        if ev.get("work_date"):
            job["work_date"] = ev.get("work_date")
    elif event == "day_ok":
        job["last_day"] = ev.get("work_date")
        job["last_count"] = ev.get("count")
    elif event == "day_err":
        job.setdefault("day_errors", []).append(ev.get("message") or "")
    elif event == "done":
        job["status"] = "done" if ev.get("success") else "error"
        job["result"] = {
            "success": ev.get("success"),
            "sync": ev.get("sync"),
            "error": ev.get("error"),
            "logs": ev.get("logs"),
        }
        if ev.get("message"):
            job["message"] = ev.get("message")
    elif event == "error":
        job["status"] = "error"
        job["message"] = ev.get("message") or "Σφάλμα"
        job["result"] = {
            "success": False,
            "error": ev.get("message"),
            "logs": ev.get("logs"),
        }


def create_portal_sync_job(*, label: str = "portal_sync") -> str:
    job_id = str(uuid.uuid4())
    with _lock:
        _jobs[job_id] = {
            "id": job_id,
            "status": "running",
            "label": label,
            "message": "Έναρξη συγχρονισμού…",
            "step": 0,
            "total": 0,
            "result": None,
        }
    return job_id


def run_portal_sync_job(
    job_id: str,
    events_fn: Callable[[], Iterator[dict[str, Any]]],
) -> None:
    def run() -> None:
        try:
            for ev in events_fn():
                with _lock:
                    job = _jobs.get(job_id)
                    if job:
                        _apply_event(job, ev)
                if ev.get("event") in ("done", "error"):
                    break
        except Exception as ex:
            with _lock:
                job = _jobs.get(job_id)
                if job:
                    job["status"] = "error"
                    job["message"] = str(ex)
                    job["result"] = {"success": False, "error": str(ex)}

    threading.Thread(target=run, daemon=True).start()


def start_portal_sync_job(
    events_fn: Callable[[], Iterator[dict[str, Any]]],
    *,
    label: str = "portal_sync",
) -> str:
    job_id = create_portal_sync_job(label=label)
    run_portal_sync_job(job_id, events_fn)
    return job_id


def get_sync_job(job_id: str) -> dict[str, Any] | None:
    with _lock:
        job = _jobs.get(job_id)
        return copy.deepcopy(job) if job else None
