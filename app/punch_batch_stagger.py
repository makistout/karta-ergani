"""Stagger submitted punch times in multi-punch batches (50–100 sec apart)."""

from __future__ import annotations

import random
from datetime import timedelta
from typing import Any

from app.work_card_payload import parse_event_at

BATCH_PUNCH_GAP_MIN_SECONDS = 50
BATCH_PUNCH_GAP_MAX_SECONDS = 100


def cumulative_stagger_seconds(punch_index: int, *, rng: Any | None = None) -> int:
    """Cumulative second offset for punch_index (0-based) from the first punch."""
    if punch_index <= 0:
        return 0
    r = rng if rng is not None else random
    total = 0
    for _ in range(punch_index):
        total += int(r.randint(BATCH_PUNCH_GAP_MIN_SECONDS, BATCH_PUNCH_GAP_MAX_SECONDS))
    return total


def precompute_batch_offsets(punch_total: int, *, rng: Any | None = None) -> list[int]:
    """
    Δευτερόλεπτα offset ανά χτύπημα (0-based) για ολόκληρη παρτίδα.
    1ο=0, κάθε επόμενο = προηγούμενο +50…100″.
    """
    total = max(0, int(punch_total or 0))
    if total <= 0:
        return []
    r = rng if rng is not None else random
    offsets = [0]
    for _ in range(1, total):
        offsets.append(
            offsets[-1] + int(r.randint(BATCH_PUNCH_GAP_MIN_SECONDS, BATCH_PUNCH_GAP_MAX_SECONDS))
        )
    return offsets


def first_punch_seconds_jitter(*, rng: Any | None = None) -> int:
    """Τυχαία δευτερόλεπτα 0–59 ώστε η βάση HH:MM να μην είναι :00."""
    r = rng if rng is not None else random
    return int(r.randint(0, 59))


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
    base_jitter_seconds: int = 0,
) -> str:
    """
    Μετατοπίζει την ώρα χτυπήματος ανά δείκτη batch.

    1ο χτύπημα στη βάση (+ προαιρετικό jitter δευτερολέπτων), κάθε επόμενο +50–100″.
    """
    raw = str(event_at_str or "").strip()
    if not raw:
        return raw
    extra = int(base_jitter_seconds or 0)
    if punch_total > 1 and punch_index > 0:
        extra += cumulative_stagger_seconds(punch_index, rng=rng)
    if extra <= 0:
        return raw
    dt = parse_event_at(raw, reference_date)
    return (dt + timedelta(seconds=extra)).isoformat(timespec="seconds")


def apply_batch_stagger_to_clock_hm(
    hm: str,
    *,
    punch_index: int,
    punch_total: int,
    rng: Any | None = None,
) -> str:
    """HH:MM με προώθηση +50–100″ ανά χτύπημα (στρογγυλοποίηση στο λεπτό)."""
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
    total_sec = h * 3600 + m * 60 + cumulative_stagger_seconds(punch_index, rng=rng)
    total_sec %= 24 * 3600
    hh, rem = divmod(total_sec, 3600)
    mm, _ = divmod(rem, 60)
    return f"{hh:02d}:{mm:02d}"
