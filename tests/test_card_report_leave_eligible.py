from app.card_report import _is_leave_eligible


def _eligible(*, now_min: int, s_start: int = 10 * 60, tol: int = 0) -> bool:
    sched = {"shift_type": "ΕΡΓ", "hour_from": "10:00", "hour_to": "16:00"}
    return _is_leave_eligible(
        sched=sched,
        wl=None,
        card_in=None,
        card_out=None,
        s_start=s_start,
        now_min=now_min,
        tol=tol,
    )


def test_leave_eligible_before_shift_start():
    assert _eligible(now_min=9 * 60 + 59) is True


def test_leave_not_eligible_at_or_after_shift_start():
    assert _eligible(now_min=10 * 60) is False
    assert _eligible(now_min=11 * 60 + 15) is False


def test_leave_not_eligible_after_tolerance_window():
    assert _eligible(now_min=10 * 60 + 16, tol=15) is False
