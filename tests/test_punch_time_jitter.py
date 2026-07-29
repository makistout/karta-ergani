from __future__ import annotations

from app.punch_time_jitter import (
    PUNCH_TIME_JITTER_MINUTES,
    apply_punch_time_jitter,
    jitter_clock_hm,
    punch_time_jitter_offset,
)


class _FixedRng:
    def __init__(self, value: int):
        self.value = value

    def randint(self, a: int, b: int) -> int:
        assert a <= self.value <= b
        return self.value


def test_punch_time_jitter_range():
    for _ in range(40):
        off = punch_time_jitter_offset()
        assert -PUNCH_TIME_JITTER_MINUTES <= off <= PUNCH_TIME_JITTER_MINUTES


def test_apply_punch_time_jitter_keeps_absolute_minutes():
    assert apply_punch_time_jitter(8 * 60 + 2, rng=_FixedRng(3)) == 8 * 60 + 5
    assert apply_punch_time_jitter(16 * 60 + 2, rng=_FixedRng(-3)) == 15 * 60 + 59
    # overnight-capable: no day wrap here
    assert apply_punch_time_jitter(24 * 60 + 2, rng=_FixedRng(-5)) == 24 * 60 - 3


def test_jitter_clock_hm():
    assert jitter_clock_hm("08:02", rng=_FixedRng(0)) == "08:02"
    assert jitter_clock_hm("16:02", rng=_FixedRng(-3)) == "15:59"
    assert jitter_clock_hm("16:02", rng=_FixedRng(3)) == "16:05"
    assert jitter_clock_hm("00:02", rng=_FixedRng(-5)) == "23:57"
