"""Tests για αυτόματη λήξη ανοιχτών assistant tasks."""

from app.repo_telegram_assistant import OPEN_ASSISTANT_TASK_TTL_SEC, expire_stale_open_assistant_tasks


def test_open_task_ttl_is_three_minutes():
    assert OPEN_ASSISTANT_TASK_TTL_SEC == 180


def test_expire_stale_open_assistant_tasks_cancels_ids(monkeypatch):
    cancelled: list[tuple[int, str]] = []

    class _Cur:
        def execute(self, *_args, **_kwargs):
            return None

        def fetchall(self):
            return [(101,), (99,)]

    class _Ctx:
        def __enter__(self):
            return _Cur()

        def __exit__(self, *_args):
            return False

    monkeypatch.setattr("app.repo_telegram_assistant.cursor", lambda **_kwargs: _Ctx())
    monkeypatch.setattr(
        "app.repo_telegram_assistant.cancel_assistant_task",
        lambda task_id, reason="user_cancelled": cancelled.append((int(task_id), reason)) or True,
    )

    ids = expire_stale_open_assistant_tasks(chat_id="6809632515", reason="expired_idle")
    assert ids == [101, 99]
    assert cancelled == [(101, "expired_idle"), (99, "expired_idle")]


def test_expire_stale_requires_scope():
    assert expire_stale_open_assistant_tasks() == []
