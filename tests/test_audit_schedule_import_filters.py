from app.audit_log import _audit_kind_filters


def test_schedule_changes_excludes_excel_batch_events():
    where, params = _audit_kind_filters(kind="schedule_changes")

    assert "wto_daily.schedule_change" in where
    assert "schedule_import" not in where
    assert params == []


def test_schedule_imports_selects_one_batch_audit_event():
    where, params = _audit_kind_filters(kind="schedule_imports")

    assert "schedule_import.batch_applied" in where
    assert params == []
