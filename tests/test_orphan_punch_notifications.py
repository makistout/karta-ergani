"""Tests for morning orphan-punch notifications (10:00 → yesterday)."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import patch

from app.orphan_punch_notifications import (
    collect_orphan_punches_for_date,
    format_orphan_punch_digest,
    should_run_orphan_punch_notify,
)


def test_should_run_after_1000_once_per_day():
    cfg = {"id": 7, "name": "Demo"}
    with (
        patch(
            "app.orphan_punch_notifications.Config.KARTA_SCHEDULED_ORPHAN_PUNCH_NOTIFY_ENABLED",
            True,
        ),
        patch(
            "app.orphan_punch_notifications.Config.KARTA_SCHEDULED_ORPHAN_PUNCH_NOTIFY_TIME",
            "10:00",
        ),
        patch("app.scheduled_sync.repo_sync_log.tables_available", return_value=True),
        patch("app.scheduled_sync._operation_run_exists", return_value=False),
    ):
        ok, target, reason = should_run_orphan_punch_notify(
            cfg,
            now=datetime(2026, 9, 26, 10, 5),
        )
    assert ok is True
    assert target == "2026-09-25"
    assert reason == "έτοιμο"


def test_should_not_run_before_1000():
    cfg = {"id": 7, "name": "Demo"}
    with (
        patch(
            "app.orphan_punch_notifications.Config.KARTA_SCHEDULED_ORPHAN_PUNCH_NOTIFY_ENABLED",
            True,
        ),
        patch(
            "app.orphan_punch_notifications.Config.KARTA_SCHEDULED_ORPHAN_PUNCH_NOTIFY_TIME",
            "10:00",
        ),
    ):
        ok, target, reason = should_run_orphan_punch_notify(
            cfg,
            now=datetime(2026, 9, 26, 9, 45),
        )
    assert ok is False
    assert target == "2026-09-25"
    assert "10:00" in reason


def test_should_skip_when_already_run_today():
    cfg = {"id": 7, "name": "Demo"}
    with (
        patch(
            "app.orphan_punch_notifications.Config.KARTA_SCHEDULED_ORPHAN_PUNCH_NOTIFY_ENABLED",
            True,
        ),
        patch(
            "app.orphan_punch_notifications.Config.KARTA_SCHEDULED_ORPHAN_PUNCH_NOTIFY_TIME",
            "10:00",
        ),
        patch("app.scheduled_sync.repo_sync_log.tables_available", return_value=True),
        patch("app.scheduled_sync._operation_run_exists", return_value=True),
    ):
        ok, target, reason = should_run_orphan_punch_notify(
            cfg,
            now=datetime(2026, 9, 26, 10, 30),
        )
    assert ok is False
    assert target == "2026-09-25"
    assert "ήδη" in reason


def test_collect_includes_open_entry_and_overnight_exit():
    cfg = {"id": 3, "name": "EKIBEN II"}
    rows = [
        {
            "employee_afm": "201980886",
            "eponymo": "BAGUNAS",
            "onoma": "ATOLIN",
            "work_date": "25/09/2026",
            "hour_from": "17:01",
            "hour_to": "",
        },
        {
            "employee_afm": "111111111",
            "eponymo": "ΜΟΝΗ",
            "onoma": "ΕΞΟΔΟΣ",
            "work_date": "26/09/2026",
            "hour_from": "",
            "hour_to": "01:04",
        },
        {
            "employee_afm": "333333333",
            "eponymo": "ΧΘΕΣ",
            "onoma": "ΕΞΟΔΟΣ",
            "work_date": "25/09/2026",
            "hour_from": "",
            "hour_to": "18:22",
        },
        {
            "employee_afm": "222222222",
            "eponymo": "ΟΛΟΚΛΗΡΗ",
            "onoma": "ΜΕΡΑ",
            "work_date": "25/09/2026",
            "hour_from": "09:00",
            "hour_to": "17:00",
        },
    ]
    with (
        patch(
            "app.orphan_punch_notifications.store_api_context",
            return_value={"employer_afm": "802788173", "branch_aa": "3"},
        ),
        patch(
            "app.repo_work_log_core.list_work_log_for_range",
            return_value=rows,
        ),
    ):
        hits = collect_orphan_punches_for_date(cfg, date_iso="2026-09-25")
    kinds = {hit["kind"] for hit in hits}
    labels = [hit["label"] for hit in hits]
    assert "open_entry" in kinds
    assert "overnight_exit" in kinds
    assert "exit_only" in kinds
    assert any("17:01" in label and "χωρίς έξοδο" in label for label in labels)
    assert any("01:04" in label and "μετά τα μεσάνυχτα" in label for label in labels)
    assert any("18:22" in label and "χωρίς είσοδο" in label for label in labels)
    assert all(hit["employee_afm"] != "222222222" for hit in hits)


def test_collect_merges_overnight_pair_and_skips():
    cfg = {"id": 3, "name": "EKIBEN II"}
    rows = [
        {
            "employee_afm": "201980886",
            "eponymo": "BAGUNAS",
            "onoma": "ATOLIN",
            "work_date": "25/09/2026",
            "hour_from": "17:01",
            "hour_to": "",
        },
        {
            "employee_afm": "201980886",
            "eponymo": "BAGUNAS",
            "onoma": "ATOLIN",
            "work_date": "26/09/2026",
            "hour_from": "",
            "hour_to": "01:04",
        },
    ]
    with (
        patch(
            "app.orphan_punch_notifications.store_api_context",
            return_value={"employer_afm": "802788173", "branch_aa": "3"},
        ),
        patch(
            "app.repo_work_log_core.list_work_log_for_range",
            return_value=rows,
        ),
    ):
        hits = collect_orphan_punches_for_date(cfg, date_iso="2026-09-25")
    assert hits == []


def test_digest_lists_orphan_labels():
    text = format_orphan_punch_digest(
        store_name="EKIBEN II",
        work_date_ergani="25/09/2026",
        hits=[
            {
                "employee_afm": "201980886",
                "name": "BAGUNAS ATOLIN",
                "label": "είσοδος 17:01 χωρίς έξοδο",
            },
            {
                "employee_afm": "111111111",
                "name": "ΜΟΝΗ ΕΞΟΔΟΣ",
                "label": "έξοδος 01:04 χωρίς είσοδο (μετά τα μεσάνυχτα)",
            },
        ],
    )
    assert "EKIBEN II" in text
    assert "25/09/2026" in text
    assert "BAGUNAS ATOLIN" in text
    assert "01:04" in text
    assert "μετά τα μεσάνυχτα" in text
