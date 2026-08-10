from flask import Flask

from app.client_request import observed_peer_ip
from app import submission_identity


def test_observed_peer_ip_ignores_spoofable_forwarded_for():
    app = Flask(__name__)
    with app.test_request_context(
        "/", environ_base={"REMOTE_ADDR": "10.0.0.8"},
        headers={"X-Forwarded-For": "203.0.113.99", "X-ARR-ClientIP": "198.51.100.20"},
    ):
        assert observed_peer_ip() == "198.51.100.20"


def test_server_identity_prefers_configured_egress_ip(monkeypatch):
    monkeypatch.setattr(submission_identity.Config, "ERGANI_EGRESS_IP", "198.51.100.44")
    monkeypatch.setattr(submission_identity.Config, "SERVER_INSTANCE_ID", "node-west-2")
    assert submission_identity.server_submission_identity() == ("198.51.100.44", "node-west-2")


def test_server_identity_never_performs_runtime_ip_lookup(monkeypatch):
    monkeypatch.setattr(submission_identity.Config, "ERGANI_EGRESS_IP", "")
    monkeypatch.setattr(submission_identity.Config, "SERVER_INSTANCE_ID", "node-without-config")
    assert submission_identity.server_submission_identity() == (None, "node-without-config")
