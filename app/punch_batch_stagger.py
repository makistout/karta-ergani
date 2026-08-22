"""Stagger submitted punch times in multi-punch batches (1–2 min apart)."""

from __future__ import annotations

import random
from datetime import timedelta
from typing import Any

from app.work_card_payload import parse_event_at

BATCH_PUNCH_GAP_MIN_MINUTES = 1
BATCH_PUNCH_GAP_MAX_MINUTES = 2


def cumulative_stagger_minutes(punch_index: int, *, rng: Any | None = None) -> int:
    """Cumulative minute offset for punch_index (0-based) from the first punch."""
    if punch_index <= 0:
        return 0
    r = rng if rng is not None else random
    total = 0
    for _ in range(punch_index):
        total += int(r.randint(BATCH_PUNCH_GAP_MIN_MINUTES, BATCH_PUNCH_GAP_MAX_MINUTES))
    return total


def count_card_punches_in_commands(commands: list[dict[str, Any]]) -> int:
    total = 0
    for cmd in commands:
        if not isinstance(cmd, dict):
            continue
        intent = str(cmd.get("intent") or "")
        if not intent.startswith("card_check_"):
            continue
        afms = cmd.get("employee_afms")
        if not isinstance(afms, list):
            afms = [cmd.get("employee_afm")] if cmd.get("employee_afm") else []
        total += len([str(a or "").strip() for a in afms if str(a or "").strip()])
    return total


def apply_batch_stagger_to_event_at(
    event_at_str: str | None,
    *,
    reference_date: str,
    punch_index: int,
    punch_total: int,
    rng: Any | None = None,
) -> str:
    """
    Μετατοπίζει την ώρα χτυπήματος ανά δείκτη batch (μόνο ετεροχρονισμένα).

    1ο χτύπημα στην ρητή ώρα, κάθε επόμενο +1–2 λεπτά.
    """
    if punch_total <= 1 or punch_index <= 0 or not event_at_str:
        return str(event_at_str or "").strip()

    offset = cumulative_stagger_minutes(punch_index, rng=rng)
    if offset <= 0:
        return str(event_at_str).strip()
    dt = parse_event_at(str(event_at_str).strip(), reference_date)
    return (dt + timedelta(minutes=offset)).isoformat(timespec="seconds")


def apply_batch_stagger_to_clock_hm(
    hm: str,
    *,
    punch_index: int,
    punch_total: int,
    rng: Any | None = None,
) -> str:
    """HH:MM με προώθηση +1–2 λεπτά ανά χτύπημα (retro batches)."""
    raw = str(hm or "").strip()
    if punch_total <= 1 or punch_index <= 0 or not raw:
        return raw
    parts = raw.replace(".", ":").split(":")
    try:
        h = int(parts[0])
        m = int(parts[1]) if len(parts) > 1 else 0
    except (ValueError, IndexError):
        return raw
    if h < 0 or h > 23 or m < 0 or m > 59:
        return raw[:5] if len(raw) >= 5 else raw
    total_min = h * 60 + m + cumulative_stagger_minutes(punch_index, rng=rng)
    total_min %= 24 * 60
    hh, mm = divmod(total_min, 60)
    return f"{hh:02d}:{mm:02d}"
