from __future__ import annotations

from app.user_terms import CURRENT_TERMS_VERSION, terms_payload


def test_terms_payload_has_placeholder_text():
    payload = terms_payload()
    assert payload["version"] == CURRENT_TERMS_VERSION
    assert "νόμιμης χρήσης" in payload["title"].lower()
    assert "ΕΡΓΑΝΗ" in payload["body_plain"]
    assert "erganios.gr" in payload["body_plain"]
    assert "εξουσιοδότηση" in payload["checkbox_label"]
    assert "<h3>" in payload["body_html"]
    assert "Απαγορευμένες χρήσεις" in payload["body_html"]


def test_onboarding_flags_without_columns(monkeypatch):
    import app.repo_users as repo_users

    monkeypatch.setattr(repo_users, "onboarding_available", lambda: False)
    flags = repo_users._onboarding_flags_from_row({"must_change_password": 1})
    assert flags["must_change_password"] is False
    assert flags["terms_accepted"] is True


def test_onboarding_flags_from_row(monkeypatch):
    import app.repo_users as repo_users

    monkeypatch.setattr(repo_users, "onboarding_available", lambda: True)
    flags = repo_users._onboarding_flags_from_row({
        "must_change_password": 1,
        "terms_accepted_at": None,
        "terms_accepted_ip": None,
        "terms_version": None,
    })
    assert flags["must_change_password"] is True
    assert flags["terms_accepted"] is False

    flags2 = repo_users._onboarding_flags_from_row({
        "must_change_password": 0,
        "terms_accepted_at": "2026-08-03T10:00:00",
        "terms_accepted_ip": "1.2.3.4",
        "terms_version": CURRENT_TERMS_VERSION,
    })
    assert flags2["must_change_password"] is False
    assert flags2["terms_accepted"] is True
    assert flags2["terms_accepted_ip"] == "1.2.3.4"


def test_onboarding_redirect_path(monkeypatch):
    from flask import Flask

    import app.office_auth as office_auth

    app = Flask(__name__)
    app.secret_key = "test"
    with app.test_request_context("/"):
        from flask import session

        session[office_auth.SESSION_LOGGED_IN] = True
        session[office_auth.SESSION_MUST_CHANGE_PASSWORD] = True
        session[office_auth.SESSION_TERMS_ACCEPTED] = False
        assert office_auth.onboarding_redirect_path() == "/ui/change-password"

        session[office_auth.SESSION_MUST_CHANGE_PASSWORD] = False
        assert office_auth.onboarding_redirect_path() == "/ui/accept-terms"

        session[office_auth.SESSION_TERMS_ACCEPTED] = True
        assert office_auth.onboarding_redirect_path() is None


def test_verification_email_mentions_password_change():
    from app.user_email_verification import build_verification_email

    text, html_body = build_verification_email(
        username="demo",
        full_name="Demo User",
        url="https://example.test/ui/verify-email?t=abc",
        temporary_password="Secret99",
    )
    assert "Secret99" in text
    assert "αλλαγή κωδικού" in text
    assert "όρων" in text
    assert "αλλαγή κωδικού" in html_body
