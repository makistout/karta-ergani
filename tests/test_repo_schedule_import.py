"""Regression tests for schedule import preview summaries."""

from __future__ import annotations

import app.repo_schedule_import as repo


def test_preview_keeps_import_action_when_recalculating_apply(monkeypatch):
    monkeypatch.setattr(repo, "get_import_batch", lambda *_args, **_kwargs: {
        "id": 16,
        "store_id": 4,
        "created_at": None,
        "applied_at": None,
        "summary_json": "{}",
    })
    monkeypatch.setattr(repo, "list_import_rows", lambda _batch_id: [{
        "change_kind": "new",
        "import_action": "work",
        "validation_errors": [],
    }])

    preview = repo.preview_import_batch(16, store_id=4)

    assert preview is not None
    assert preview["summary"]["new"] == 1
    assert preview["summary"]["apply"] == 1
