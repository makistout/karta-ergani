"""API εργαζομένων — ξεχωριστό blueprint."""

from __future__ import annotations

from flask import Blueprint, jsonify, request

from app.http_helpers import resolve_active_store
from app.repo_entities import list_employees_for_employer

employees_bp = Blueprint("employees", __name__, url_prefix="/api/employees")


@employees_bp.get("/list")
def employees_list():
    ctx = resolve_active_store()
    if not ctx:
        return jsonify({"error": "Επιλέξτε πρώτα κατάστημα", "employees": []}), 400
    try:
        lim = int(request.args.get("limit", "2000"))
    except ValueError:
        lim = 2000
    rows = list_employees_for_employer(
        str(ctx["employer_afm"]),
        branch_aa=str(ctx.get("branch_aa") or "0"),
        limit=lim,
    )
    for r in rows:
        if hasattr(r.get("updated_at"), "isoformat"):
            r["updated_at"] = r["updated_at"].isoformat()
    return jsonify({
        "store": {
            "id": ctx["id"],
            "name": ctx["name"],
            "employer_afm": ctx["employer_afm"],
            "branch_aa": ctx.get("branch_aa"),
        },
        "employer_afm": ctx["employer_afm"],
        "branch_aa": ctx.get("branch_aa"),
        "count": len(rows),
        "employees": rows,
        "hint": (
            "Οι εργαζόμενοι συνδέονται με εργοδότη μέσω karta_employment "
            "(όχι απευθείας στο karta_employee). Η λίστα φιλτράρεται από το ενεργό σημείο."
        ),
    })
