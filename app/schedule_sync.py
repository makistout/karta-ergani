"""Συγχρονισμός ψηφιακού ωραρίου — portal Ergani (Τρέχουσα Κατάσταση)."""

from __future__ import annotations

import re
from typing import Any

from app.date_util import iso_to_ergani_dates
from app.portal_schedule_sync import sync_schedule_from_portal


def fetch_and_save_schedule(
    bearer: str | None,
    employer_afm: str,
    branch_aa: str,
    date_input: str | None = None,
    *,
    api_base_url: str | None = None,
    store_ctx: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Συγχρονισμός μίας ημέρας μέσω portal (bearer/api_base_url αγνοούνται)."""
    del bearer, employer_afm, branch_aa, api_base_url
    if not store_ctx:
        return {
            "success": False,
            "detail": "Λείπει store_ctx για portal sync",
            "count": 0,
            "source": "portal",
        }
    from_iso = None
    if date_input:
        s = str(date_input).strip()[:10]
        if re.match(r"^\d{4}-\d{2}-\d{2}$", s):
            from_iso = s
    return sync_schedule_from_portal(store_ctx, from_iso=from_iso, to_iso=from_iso, max_days=1)


def fetch_and_save_schedule_range(
    bearer: str | None,
    employer_afm: str,
    branch_aa: str,
    from_iso: str,
    to_iso: str,
    max_days: int = 31,
    *,
    api_base_url: str | None = None,
    store_ctx: dict[str, Any] | None = None,
) -> dict[str, Any]:
    del bearer, employer_afm, branch_aa, api_base_url
    if not store_ctx:
        return {
            "success": False,
            "detail": "Λείπει store_ctx για portal sync",
            "count": 0,
            "source": "portal",
        }
    return sync_schedule_from_portal(
        store_ctx,
        from_iso=from_iso,
        to_iso=to_iso,
        max_days=max_days,
    )


def fetch_and_save_schedule_for_ctx(
    ctx: dict[str, Any],
    from_iso: str | None = None,
    to_iso: str | None = None,
    *,
    max_days: int = 31,
) -> dict[str, Any]:
    """Κύρια είσοδος: ενεργό κατάστημα + ISO ημερομηνίες."""
    if from_iso and to_iso and from_iso != to_iso:
        dates = iso_to_ergani_dates(from_iso, to_iso, max_days)
        if len(dates) > 1:
            return sync_schedule_from_portal(ctx, from_iso=from_iso, to_iso=to_iso, max_days=max_days)
    return sync_schedule_from_portal(ctx, from_iso=from_iso, to_iso=to_iso, max_days=max_days)
