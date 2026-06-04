"""Τοπικά δεδομένα από MSSQL ergani-karta."""

from __future__ import annotations

from flask import Blueprint, jsonify, request

from app.repo_card import list_card_events
from app.repo_entities import list_employees
from app.routes_work_card import work_card_info, work_card_post_event

local_bp = Blueprint("local", __name__, url_prefix="/api/local")


@local_bp.get("/health")
def local_health():
    from config import Config

    return jsonify({
        "ok": True,
        "database": Config.DB_DATABASE,
        "db_driver": "pyodbc",
    })


@local_bp.get("/employees")
def local_employees():
    return jsonify(list_employees())


@local_bp.get("/work-card/events")
def local_work_card_events():
    try:
        n = int(request.args.get("limit", "100"))
    except ValueError:
        n = 100
    return jsonify(list_card_events(n))


@local_bp.get("/work-card/info")
def local_work_card_info():
    return work_card_info()


@local_bp.post("/work-card/event")
def local_work_card_event():
    return work_card_post_event()
