"""Tests for evening contract-overage notifications (21:00 → tomorrow)."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import patch

from app.contract_home_alerts import CODE_HOURS_OVER, CODE_SIXTH_DAY
from app.contract_overage_notifications import (
    format_contract_overage_digest,
    should_run_contract_overage_notify,
)


def test_should_run_after_2100_once_per_day():
    cfg = {"id": 7, "name": "Demo"}
    with (
        patch(
            "app.contract_overage_notifications.Config.KARTA_SCHEDULED_CONTRACT_OVERAGE_NOTIFY_ENABLED",
            True,
        ),
        patch(
            "app.contract_overage_notifications.Config.KARTA_SCHEDULED_CONTRACT_OVERAGE_NOTIFY_TIME",
            "21:00",
        ),
        patch("app.scheduled_sync.repo_sync_log.tables_available", return_value=True),
        patch("app.scheduled_sync._operation_run_exists", return_value=False),
    ):
        ok, target, reason = should_run_contract_overage_notify(
            cfg,
            now=datetime(2026, 9, 15, 21, 5),
        )
    assert ok is True
    assert target == "2026-09-16"
    assert reason == "έτοιμο"


def test_should_not_run_before_2100():
    cfg = {"id": 7, "name": "Demo"}
    with (
        patch(
            "app.contract_overage_notifications.Config.KARTA_SCHEDULED_CONTRACT_OVERAGE_NOTIFY_ENABLED",
            True,
        ),
        patch(
            "app.contract_overage_notifications.Config.KARTA_SCHEDULED_CONTRACT_OVERAGE_NOTIFY_TIME",
            "21:00",
        ),
    ):
        ok, target, reason = should_run_contract_overage_notify(
            cfg,
            now=datetime(2026, 9, 15, 20, 45),
        )
    assert ok is False
    assert target == "2026-09-16"
    assert "21:00" in reason


def test_should_skip_when_already_run_today():
    cfg = {"id": 7, "name": "Demo"}
    with (
        patch(
            "app.contract_overage_notifications.Config.KARTA_SCHEDULED_CONTRACT_OVERAGE_NOTIFY_ENABLED",
            True,
        ),
        patch(
            "app.contract_overage_notifications.Config.KARTA_SCHEDULED_CONTRACT_OVERAGE_NOTIFY_TIME",
            "21:00",
        ),
        patch("app.scheduled_sync.repo_sync_log.tables_available", return_value=True),
        patch("app.scheduled_sync._operation_run_exists", return_value=True),
    ):
        ok, target, reason = should_run_contract_overage_notify(
            cfg,
            now=datetime(2026, 9, 15, 21, 30),
        )
    assert ok is False
    assert target == "2026-09-16"
    assert "ήδη" in reason


def test_digest_lists_employees_and_labels():
    text = format_contract_overage_digest(
        store_name="ΛΑΔΟΚΟΛΛΑ",
        work_date_ergani="16/09/2026",
        hits=[
            {
                "employee_afm": "180137703",
                "name": "ΣΚΟΡΔΑ ΕΛΕΥΘΕΡΙΑ",
                "alerts": [
                    {
                        "code": CODE_HOURS_OVER,
                        "label": (
                            "Παράβαση σύμβασης: δηλωμένες 30 ώρες αυτή την εβδομάδα "
                            "ενώ η σύμβαση προβλέπει 28 ώρες (Συνολικές ώρες εβδομαδιαίως)"
                        ),
                    }
                ],
            },
            {
                "employee_afm": "111",
                "name": "ΤΕΣΤ",
                "alerts": [
                    {
                        "code": CODE_SIXTH_DAY,
                        "label": "Παράβαση σύμβασης: 6η εργάσιμη εβδομάδας ενώ η σύμβαση είναι 5ήμερη",
                    }
                ],
            },
        ],
    )
    assert "ΛΑΔΟΚΟΛΛΑ" in text
    assert "16/09/2026" in text
    assert "ΣΚΟΡΔΑ ΕΛΕΥΘΕΡΙΑ" in text
    assert "28 ώρες" in text
    assert "6η εργάσιμη" in text
