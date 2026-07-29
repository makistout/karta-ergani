"""Τυχαία προσθαφαίρεση ± λεπτά σε ώρες εισόδου/εξόδου για ρεαλιστική καταγραφή."""

from __future__ import annotations

import random
from typing import Any

PUNCH_TIME_JITTER_MINUTES = 5


def punch_time_jitter_offset(*, rng: Any | None = None) -> int:
    """Τυχαίο offset στο [-PUNCH_TIME_JITTER_MINUTES, +PUNCH_TIME_JITTER_MINUTES]."""
    r = rng if rng is not None else random
    return int(r.randint(-PUNCH_TIME_JITTER_MINUTES, PUNCH_TIME_JITTER_MINUTES))


def apply_punch_time_jitter(total_minutes: int, *, rng: Any | None = None) -> int:
    """
    Προσθαφαίρεση ±5′ σε απόλυτα λεπτά.

    Δεν κάνει wrap ημέρας — επιτρέπει <0 ή >=1440 ώστε να δουλεύει overnight λογική.
    """
    return int(total_minutes) + punch_time_jitter_offset(rng=rng)


def jitter_clock_hm(hm: str | None, *, rng: Any | None = None) -> str:
    """HH:MM (ή HH:MM:SS) → HH:MM με ±5′ (wrap εντός ημέρας)."""
    raw = str(hm or "").strip()
    if not raw:
        return ""
    parts = raw.split(":")
    try:
        h = int(parts[0])
        m = int(parts[1]) if len(parts) > 1 else 0
    except (TypeError, ValueError, IndexError):
        return raw
    if h < 0 or h > 23 or m < 0 or m > 59:
        return raw[:5] if len(raw) >= 5 else raw
    total = apply_punch_time_jitter(h * 60 + m, rng=rng)
    wrapped = total % (24 * 60)
    if wrapped < 0:
        wrapped += 24 * 60
    hh, mm = divmod(wrapped, 60)
    return f"{hh:02d}:{mm:02d}"
