"""API εισαγωγής εβδομαδιαίου ωραρίου από Excel."""

from __future__ import annotations

import pyodbc
from flask import Blueprint, jsonify, request, send_file

from app.access_control import current_user_id
from app.http_helpers import resolve_active_store
from app.repo_schedule_import import (
    create_import_batch,
    get_import_batch,
    insert_import_rows,
    preview_import_batch,
    schedule_import_table_missing_message,
    update_batch_status,
)
from app.schedule_excel_import import parse_weekly_schedule_workbook
from app.schedule_excel_template import build_weekly_schedule_template_bytes, resolve_week_monday
from app.schedule_import_service import confirm_import_batch

schedule_import_bp = Blueprint("schedule_import", __name__, url_prefix="/api/schedule/import")


def _import_db_error(exc: Exception):
    msg = schedule_import_table_missing_message(exc)
    if msg:
        return jsonify({"error": msg, "db_setup": "sql/alter_add_schedule_import_staging.sql"}), 503
    raise exc


@schedule_import_bp.route("/template", methods=["GET"])
def download_schedule_import_template():
    ctx = resolve_active_store()
    if not ctx:
        return jsonify({"error": "Επιλέξτε πρώτα κατάστημα"}), 400

    week = str(request.args.get("week") or "current").strip().lower()
    try:
        week_monday = resolve_week_monday(week)
        content, filename, _meta = build_weekly_schedule_template_bytes(
            store_id=int(ctx["id"]),
            week_monday=week_monday,
        )
    except ValueError as ex:
        return jsonify({"error": str(ex)}), 400
    except Exception as ex:
        return jsonify({"error": f"Αποτυχία δημιουργίας template: {ex}"}), 500

    from io import BytesIO

    response = send_file(
        BytesIO(content),
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=filename,
    )
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    return response


@schedule_import_bp.post("/upload")
def upload_schedule_import():
    ctx = resolve_active_store()
    if not ctx:
        return jsonify({"error": "Επιλέξτε πρώτα κατάστημα"}), 400

    upload = request.files.get("file")
    if upload is None or not upload.filename:
        return jsonify({"error": "Λείπει αρχείο Excel"}), 400
    if not str(upload.filename).lower().endswith(".xlsx"):
        return jsonify({"error": "Επιτρέπεται μόνο αρχείο .xlsx"}), 400

    raw = upload.read()
    if not raw:
        return jsonify({"error": "Κενό αρχείο"}), 400
    if len(raw) > 8 * 1024 * 1024:
        return jsonify({"error": "Το αρχείο υπερβαίνει το όριο 8MB"}), 400

    try:
        parsed = parse_weekly_schedule_workbook(
            raw,
            employer_afm=str(ctx["employer_afm"]),
            branch_aa=str(ctx.get("branch_aa") or "0"),
        )
    except ValueError as ex:
        return jsonify({"error": str(ex)}), 400
    except Exception as ex:
        return jsonify({"error": f"Αποτυχία ανάγνωσης Excel: {ex}"}), 400

    meta = parsed.get("meta") if isinstance(parsed.get("meta"), dict) else {}
    meta_store_id = meta.get("store_id")
    if meta_store_id is not None and int(meta_store_id) != int(ctx["id"]):
        return jsonify(
            {
                "error": (
                    f"Το Excel αναφέρει Store ID {meta_store_id}, "
                    f"αλλά το ενεργό κατάστημα είναι {ctx['id']} ({ctx.get('name')})"
                )
            }
        ), 400

    file_errors = [str(e) for e in (parsed.get("errors") or []) if str(e).strip()]
    rows = parsed.get("rows") or []
    summary = parsed.get("summary") or {}

    try:
        batch_id = create_import_batch(
            store_id=int(ctx["id"]),
            employer_afm=str(ctx["employer_afm"]),
            branch_aa=str(ctx.get("branch_aa") or "0"),
            original_filename=str(upload.filename or "")[:255],
            week_label=str(meta.get("week_label") or "")[:128] or None,
            created_by_user_id=current_user_id(),
            summary=summary,
        )
        insert_import_rows(batch_id, rows)
        preview = preview_import_batch(batch_id, store_id=int(ctx["id"]))
    except pyodbc.Error as ex:
        return _import_db_error(ex)

    return jsonify(
        {
            "success": True,
            "batch_id": batch_id,
            "file_errors": file_errors,
            "preview": preview,
        }
    )


@schedule_import_bp.get("/preview/<int:batch_id>")
def schedule_import_preview(batch_id: int):
    ctx = resolve_active_store()
    if not ctx:
        return jsonify({"error": "Επιλέξτε πρώτα κατάστημα"}), 400
    try:
        preview = preview_import_batch(batch_id, store_id=int(ctx["id"]))
    except pyodbc.Error as ex:
        return _import_db_error(ex)
    if not preview:
        return jsonify({"error": "Δεν βρέθηκε η εισαγωγή"}), 404
    return jsonify(preview)


@schedule_import_bp.post("/confirm/<int:batch_id>")
def schedule_import_confirm(batch_id: int):
    ctx = resolve_active_store()
    if not ctx:
        return jsonify({"error": "Επιλέξτε πρώτα κατάστημα"}), 400
    try:
        result = confirm_import_batch(ctx, batch_id)
    except pyodbc.Error as ex:
        return _import_db_error(ex)
    status = 200 if result.get("success") else 502
    if result.get("error") and result.get("applied", 0) == 0 and result.get("failed", 0) == 0:
        status = 400
    return jsonify(result), status


@schedule_import_bp.post("/cancel/<int:batch_id>")
def schedule_import_cancel(batch_id: int):
    ctx = resolve_active_store()
    if not ctx:
        return jsonify({"error": "Επιλέξτε πρώτα κατάστημα"}), 400
    batch = get_import_batch(batch_id, store_id=int(ctx["id"]))
    if not batch:
        return jsonify({"error": "Δεν βρέθηκε η εισαγωγή"}), 404
    if str(batch.get("status") or "") != "preview":
        return jsonify({"error": "Η εισαγωγή δεν είναι σε προεπισκόπηση"}), 400
    try:
        update_batch_status(batch_id, "cancelled")
    except pyodbc.Error as ex:
        return _import_db_error(ex)
    return jsonify({"success": True})
