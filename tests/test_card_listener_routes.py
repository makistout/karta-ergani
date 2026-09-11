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


def test_listener_job_long_poll_is_capped_at_eight_seconds():
    device = {"id": 9, "store_id": 27, "device_id": "18cbf129-0939-4e98-85b5-b2215153eceb", "last_seen_ip": None}
    with (
        patch("app.routes_card_listener.repo.authenticate_device", return_value=device),
        patch("app.routes_card_listener.repo.lease_next_job", return_value=None),
        patch("app.routes_card_listener.time.monotonic", side_effect=[100.0, 108.0]),
        patch("app.routes_card_listener.time.sleep") as sleep,
    ):
        response = _app().test_client().get("/api/card-listener/v1/jobs/next?wait=25")
    assert response.status_code == 200
    assert response.json["job"] is None
    sleep.assert_not_called()


def test_setup_rar_download_serves_attachment(tmp_path):
    from app.routes_card_listener import listener_download_bp

    setup = tmp_path / "setup.rar"
    setup.write_bytes(b"Rar!\x00fake-listener-setup")
    app = Flask(__name__)
    app.register_blueprint(listener_download_bp)
    with patch("app.routes_card_listener._LISTENER_SETUP_RAR", setup):
        response = app.test_client().get("/listener/setup.rar")
    assert response.status_code == 200
    assert response.data.startswith(b"Rar!")
    assert "attachment" in (response.headers.get("Content-Disposition") or "")
    assert "setup.rar" in (response.headers.get("Content-Disposition") or "")


def test_setup_rar_download_404_when_missing(tmp_path):
    from app.routes_card_listener import listener_download_bp

    missing = tmp_path / "missing.rar"
    app = Flask(__name__)
    app.register_blueprint(listener_download_bp)
    with patch("app.routes_card_listener._LISTENER_SETUP_RAR", missing):
        response = app.test_client().get("/listener/setup.rar")
    assert response.status_code == 404
