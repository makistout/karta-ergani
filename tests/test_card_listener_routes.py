from unittest.mock import patch

from flask import Flask

from app.routes_card_listener import card_listener_bp


def _app():
    app = Flask(__name__)
    app.register_blueprint(card_listener_bp)
    return app


def test_listener_rejects_unknown_device():
    with patch("app.routes_card_listener.repo.authenticate_device", return_value=None):
        response = _app().test_client().get("/api/card-listener/v1/health")
    assert response.status_code == 401
    assert response.json["error"] == "invalid_listener_device"


def test_listener_identity_determines_store():
    device = {"id": 1, "store_id": 27, "device_id": "18cbf129-0939-4e98-85b5-b2215153eceb", "last_seen_ip": "198.51.100.88"}
    store = {"id": 27, "name": "Test", "employer_afm": "123456789", "branch_aa": "0", "ergani_env": "trial"}
    with (
        patch("app.routes_card_listener.repo.authenticate_device", return_value=device),
        patch("app.repo_store.get_store_config", return_value=store),
    ):
        response = _app().test_client().get(
            "/api/card-listener/v1/health",
            headers={
                "X-Listener-Device": device["device_id"],
                "Authorization": "Bearer device-secret",
            },
        )
    assert response.status_code == 200
    assert response.json["ok"] is True
    assert response.json["store_id"] == 27
    assert response.json["ergani_env"] == "trial"
    assert response.json["ergani_env_label"] == "Δοκιμαστικό"
    assert "trialv2eservices" in response.json["ergani_api_base_url"]


def test_listener_cannot_report_job_not_owned_by_its_store():
    device = {"id": 1, "store_id": 27, "device_id": "18cbf129-0939-4e98-85b5-b2215153eceb", "last_seen_ip": "198.51.100.88"}
    job_id = "23fc7277-94d3-4f65-9b0f-d0499d1b6e55"
    with (
        patch("app.routes_card_listener.repo.authenticate_device", return_value=device),
        patch("app.routes_card_listener.repo.finish_job", return_value=False) as finish,
    ):
        response = _app().test_client().post(
            f"/api/card-listener/v1/jobs/{job_id}/result",
            json={"success": True},
        )
    assert response.status_code == 409
    finish.assert_called_once_with(
        27, device["device_id"], job_id, {"success": True}, submission_ip="198.51.100.88"
    )


def test_listener_refreshes_public_ip_independently():
    device = {"id": 9, "store_id": 27, "device_id": "18cbf129-0939-4e98-85b5-b2215153eceb", "last_seen_ip": None}
    with (
        patch("app.routes_card_listener.repo.authenticate_device", return_value=device),
        patch("app.routes_card_listener.repo.update_device_public_ip") as update,
    ):
        response = _app().test_client().post(
            "/api/card-listener/v1/network/refresh",
            headers={"X-ARR-ClientIP": "8.8.4.4"},
        )
    assert response.status_code == 200
    assert response.json["public_ip"] == "8.8.4.4"
    update.assert_called_once_with(9, "8.8.4.4")


def test_listener_accepts_authenticated_public_ip_report():
    device = {"id": 9, "store_id": 27, "device_id": "18cbf129-0939-4e98-85b5-b2215153eceb", "last_seen_ip": None}
    with (
        patch("app.routes_card_listener.repo.authenticate_device", return_value=device),
        patch("app.routes_card_listener.repo.update_device_public_ip") as update,
    ):
        response = _app().test_client().post(
            "/api/card-listener/v1/network/refresh",
            json={"public_ip": "8.8.8.8"},
        )
    assert response.status_code == 200
    assert response.json["public_ip"] == "8.8.8.8"
    update.assert_called_once_with(9, "8.8.8.8")


def test_listener_never_stores_loopback_as_public_ip():
    device = {"id": 9, "store_id": 27, "device_id": "18cbf129-0939-4e98-85b5-b2215153eceb", "last_seen_ip": None}
    with (
        patch("app.routes_card_listener.repo.authenticate_device", return_value=device),
        patch("app.routes_card_listener.repo.update_device_public_ip") as update,
    ):
        response = _app().test_client().post(
            "/api/card-listener/v1/network/refresh",
            json={"public_ip": "127.0.0.1"},
        )
    assert response.status_code == 200
    assert response.json["public_ip"] is None
    update.assert_called_once_with(9, None)
