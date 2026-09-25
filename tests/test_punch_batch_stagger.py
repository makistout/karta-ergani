"""Tests for batch punch time stagger (50–100 sec apart)."""

from app.punch_batch_stagger import (
    apply_batch_stagger_to_clock_hm,
    apply_batch_stagger_to_event_at,
    count_card_punches_in_commands,
    cumulative_stagger_seconds,
    first_punch_seconds_jitter,
    precompute_batch_offsets,
)


class _FixedRng:
    def __init__(self, value: int = 75):
        self.value = value

    def randint(self, low, high):
        return self.value


def test_cumulative_stagger_seconds():
    assert cumulative_stagger_seconds(0) == 0
    assert cumulative_stagger_seconds(1, rng=_FixedRng(50)) == 50
    assert cumulative_stagger_seconds(2, rng=_FixedRng(75)) == 150


def test_count_card_punches_across_commands():
    commands = [
        {"intent": "card_check_in_now", "employee_afms": ["111", "222"]},
        {"intent": "rest_day", "employee_afms": ["333"]},
        {"intent": "card_check_out_now", "employee_afm": "444"},
    ]
    assert count_card_punches_in_commands(commands) == 3


def test_explicit_retro_time_staggers_forward_with_seconds():
    out = apply_batch_stagger_to_event_at(
        "2026-08-22T10:00:00",
        reference_date="2026-08-22",
        punch_index=2,
        punch_total=3,
        rng=_FixedRng(75),
        base_jitter_seconds=53,
    )
    assert out.startswith("2026-08-22T10:03:23")


def test_first_retro_punch_keeps_jitter_seconds():
    out = apply_batch_stagger_to_event_at(
        "2026-08-22T12:17:00",
        reference_date="2026-08-22",
        punch_index=0,
        punch_total=5,
        rng=_FixedRng(75),
        base_jitter_seconds=53,
    )
    assert out.startswith("2026-08-22T12:17:53")


def test_precompute_batch_offsets():
    assert precompute_batch_offsets(0) == []
    assert precompute_batch_offsets(1) == [0]
    assert precompute_batch_offsets(3, rng=_FixedRng(75)) == [0, 75, 150]


def test_first_punch_seconds_jitter_range():
    assert first_punch_seconds_jitter(rng=_FixedRng(53)) == 53


def test_clock_hm_stagger():
    assert apply_batch_stagger_to_clock_hm(
        "10:00", punch_index=2, punch_total=3, rng=_FixedRng(75),
    ) == "10:02"
