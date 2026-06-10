"""Κοινή λογική POST /sync — πάντα async για διάστημα ημερών."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any, Callable

from flask import after_this_request, jsonify

from app.date_util import iso_to_ergani_dates
from app.sync_jobs import create_portal_sync_job, run_portal_sync_job


def parse_sync_request(data: dict[str, Any]) -> tuple[str | None, str | None, list[str]]:
    from_iso = (data.get("from") or data.get("date") or "").strip()[:10] or None
    to_iso = (data.get("to") or from_iso or "").strip()[:10] or None
    if not from_iso:
        return None, None, []
    dates = iso_to_ergani_dates(from_iso, to_iso, 31)
    return from_iso, to_iso, dates


def should_run_async(data: dict[str, Any], dates: list[str]) -> bool:
    if data.get("async") in (True, "true", "1", 1):
        return True
    # Πάντα async — ώστε finish_run στη βάση και live progress
    return True


def start_async_portal_sync(
    events_fn: Callable[[str], Iterator[dict[str, Any]]],
    *,
    label: str,
    store_id: int | None = None,
):
    """Επιστρέφει job_id αμέσως — ο worker ξεκινά μετά την αποστολή της HTTP απάντησης."""
    job_id = create_portal_sync_job(label=label, store_id=store_id)

    @after_this_request
    def _start_worker(response):
        run_portal_sync_job(job_id, lambda: events_fn(job_id))
        return response

    return jsonify({"async": True, "job_id": job_id})
