from __future__ import annotations

from app.client_request import _client_ip_info, _pick_best_ip


class _FakeReq:
    def __init__(self, headers=None, remote_addr="127.0.0.1", environ=None):
        self.headers = headers or {}
        self.remote_addr = remote_addr
        self.environ = environ or {}


def test_prefers_public_xff_over_loopback_remote():
    req = _FakeReq(
        headers={"X-Forwarded-For": "8.8.8.8"},
        remote_addr="127.0.0.1",
    )
    ip, source = _client_ip_info(req)
    assert ip == "8.8.8.8"
    assert source == "X-Forwarded-For"


def test_skips_loopback_in_xff_chain():
    req = _FakeReq(
        headers={"X-Forwarded-For": "127.0.0.1, 8.8.4.4"},
        remote_addr="127.0.0.1",
    )
    ip, source = _client_ip_info(req)
    assert ip == "8.8.4.4"
    assert source == "X-Forwarded-For"


def test_pick_best_ip_public_wins():
    ip, source = _pick_best_ip([
        ("127.0.0.1", "remote_addr"),
        ("10.0.0.5", "lan"),
        ("8.8.8.8", "xff"),
    ])
    assert ip == "8.8.8.8"
    assert source == "xff"


def test_arr_client_ip_preferred_when_no_public_xff():
    req = _FakeReq(
        headers={"X-ARR-ClientIP": "8.8.4.4"},
        remote_addr="127.0.0.1",
    )
    ip, source = _client_ip_info(req)
    assert ip == "8.8.4.4"
    assert source == "X-ARR-ClientIP"
