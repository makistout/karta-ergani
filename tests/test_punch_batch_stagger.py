"""Tests for batch punch time stagger (1–2 min apart, retro only)."""

from app.punch_batch_stagger import (
    apply_batch_stagger_to_clock_hm,
    apply_batch_stagger_to_event_at,
    count_card_punches_in_commands,
    cumulative_stagger_minutes,
)


class _FixedRng:
    def __init__(self, value: int = 2):
        self.value = value

    def randint(self, low, high):
        return self.value


def test_cumulative_stagger_minutes():
    assert cumulative_stagger_minutes(0) == 0
    assert cumulative_stagger_minutes(1, rng=_FixedRng(1)) == 1
    assert cumulative_stagger_minutes(2, rng=_FixedRng(2)) == 4


def test_count_card_punches_across_commands():
    commands = [
        {"intent": "card_check_in_now", "employee_afms": ["111", "222"]},
        {"intent": "rest_day", "employee_afms": ["333"]},
        {"intent": "card_check_out_now", "employee_afm": "444"},
    ]
    assert count_card_punches_in_commands(commands) == 3


def test_explicit_retro_time_staggers_forward():
    out = apply_batch_stagger_to_event_at(
        "2026-08-22T10:00:00",
        reference_date="2026-08-22",
        punch_index=2,
        punch_total=3,
        rng=_FixedRng(2),
    )
    assert out.startswith("2026-08-22T10:04:00")


def test_first_retro_punch_unchanged():
    out = apply_batch_stagger_to_event_at(
        "2026-08-22T23:00:00",
        reference_date="2026-08-22",
        punch_index=0,
        punch_total=5,
        rng=_FixedRng(2),
    )
    assert out == "2026-08-22T23:00:00"


def test_clock_hm_stagger():
    assert apply_batch_stagger_to_clock_hm(
        "10:00", punch_index=2, punch_total=3, rng=_FixedRng(2),
    ) == "10:04"
