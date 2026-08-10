from unittest.mock import patch

from flask import Flask

from app.routes_store import store_bp


DEVICE_ID = "7155edf7-ca08-4324-b243-fd68ecd5ebee"


def _app():
    app = Flask(__name__)
    app.config.update(TESTING=True, SECRET_KEY="test")
    app.register_blueprint(store_bp)
    return app


def test_delete_offline_listener_device():
    with (
        patch("app.routes_store.can_access_store", return_value=True),
        patch("app.repo_card_listener.get_listener_settings", return_value={"listener_offline_seconds": 60}),
        patch("app.repo_card_listener.delete_offline_device", return_value=True) as delete,
    ):
        response = _app().test_client().delete(f"/api/store/27/card-listener/devices/{DEVICE_ID}")
    assert response.status_code == 200
    assert response.json == {"success": True, "deleted": True}
    delete.assert_called_once_with(27, DEVICE_ID, 60)


def test_online_listener_device_cannot_be_deleted():
    with (
        patch("app.routes_store.can_access_store", return_value=True),
        patch("app.repo_card_listener.get_listener_settings", return_value={"listener_offline_seconds": 60}),
        patch("app.repo_card_listener.delete_offline_device", return_value=False),
    ):
        response = _app().test_client().delete(f"/api/store/27/card-listener/devices/{DEVICE_ID}")
    assert response.status_code == 409
    assert "online" in response.json["error"].lower()
