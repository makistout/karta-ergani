"""Σερβίρισμα ξεχωριστών HTML σελίδων UI."""

from __future__ import annotations

from pathlib import Path

from flask import Blueprint, redirect, send_from_directory

ui_bp = Blueprint("ui", __name__, url_prefix="/ui")
_UI_DIR = Path(__file__).resolve().parent / "static" / "ui"


@ui_bp.get("/")
def ui_home():
    return send_from_directory(_UI_DIR, "home.html")


@ui_bp.get("/stores")
def ui_stores_list():
    return send_from_directory(_UI_DIR, "stores-list.html")


@ui_bp.get("/stores/credentials")
def ui_store_credentials():
    return send_from_directory(_UI_DIR, "store-credentials.html")


@ui_bp.get("/stores/branch")
def ui_store_branch():
    return send_from_directory(_UI_DIR, "store-branch.html")


@ui_bp.get("/stores/mappings")
def ui_store_mappings():
    return send_from_directory(_UI_DIR, "store-mappings.html")


@ui_bp.get("/employees")
def ui_employees_list():
    return send_from_directory(_UI_DIR, "employees-list.html")


@ui_bp.get("/schedule")
def ui_schedule_list():
    return send_from_directory(_UI_DIR, "schedule-list.html")


@ui_bp.get("/work-log")
def ui_work_log_list():
    return send_from_directory(_UI_DIR, "work-log-list.html")


@ui_bp.get("/work-card")
def ui_work_card():
    return send_from_directory(_UI_DIR, "work-card-list.html")


def register_ui_redirects(app):
    @app.get("/")
    def root_redirect():
        return redirect("/ui/")
