"""Tests για εύρος μηνών αρχείου νέου καταστήματος."""

from datetime import date

from app.portal_schedule_archive import archive_months_for_new_store, month_label_el


def test_archive_months_skipped_in_january_february():
    assert archive_months_for_new_store(date(2026, 1, 15)) == []
    assert archive_months_for_new_store(date(2026, 2, 28)) == []


def test_archive_months_march_is_january_only():
    assert archive_months_for_new_store(date(2026, 3, 1)) == [date(2026, 1, 1)]


def test_archive_months_august_through_june():
    months = archive_months_for_new_store(date(2026, 8, 20))
    assert months[0] == date(2026, 1, 1)
    assert months[-1] == date(2026, 6, 1)
    assert len(months) == 6


def test_archive_months_december_through_october():
    months = archive_months_for_new_store(date(2026, 12, 5))
    assert months[-1] == date(2026, 10, 1)
    assert len(months) == 10


def test_month_label_el():
    assert month_label_el(date(2026, 6, 1)) == "Ιούνιος 2026"
