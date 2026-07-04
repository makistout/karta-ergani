"""Public contact form endpoint."""

from __future__ import annotations

import re
import html

from flask import Blueprint, jsonify, request

from app.email_notify import EmailNotConfigured, send_email_message

contact_bp = Blueprint("contact", __name__, url_prefix="/api/contact")

CONTACT_TO_EMAIL = "info@erganios.gr"
_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def _clean(value: object, limit: int) -> str:
    return str(value or "").strip()[:limit]


@contact_bp.post("")
def submit_contact():
    data = request.get_json(silent=True) or {}
    if _clean(data.get("website"), 120):
        return jsonify({"success": True, "message": "Το μήνυμα στάλθηκε."})

    name = _clean(data.get("name"), 120)
    email = _clean(data.get("email"), 180)
    phone = _clean(data.get("phone"), 60)
    company = _clean(data.get("company"), 160)
    employees = _clean(data.get("employees"), 40)
    message = _clean(data.get("message"), 1500)

    if not name or not email or not message:
        return jsonify({"success": False, "error": "Συμπληρώστε όνομα, email και μήνυμα."}), 400
    if not _EMAIL_RE.match(email):
        return jsonify({"success": False, "error": "Συμπληρώστε έγκυρο email."}), 400

    subject = f"Νέο μήνυμα επικοινωνίας erganiOS — {name}"
    text_body = "\n".join([
        "Νέο μήνυμα από τη φόρμα επικοινωνίας erganiOS",
        "",
        f"Όνομα: {name}",
        f"Email: {email}",
        f"Τηλέφωνο: {phone or '—'}",
        f"Επιχείρηση/Γραφείο: {company or '—'}",
        f"Εύρος εργαζομένων: {employees or '—'}",
        "",
        "Μήνυμα:",
        message,
    ])
    safe = {key: html.escape(value) for key, value in {
        "name": name,
        "email": email,
        "phone": phone or "—",
        "company": company or "—",
        "employees": employees or "—",
        "message": message,
    }.items()}
    html_body = (
        "<h2>Νέο μήνυμα από τη φόρμα επικοινωνίας erganiOS</h2>"
        "<table cellpadding='6' cellspacing='0'>"
        f"<tr><td><strong>Όνομα</strong></td><td>{safe['name']}</td></tr>"
        f"<tr><td><strong>Email</strong></td><td>{safe['email']}</td></tr>"
        f"<tr><td><strong>Τηλέφωνο</strong></td><td>{safe['phone']}</td></tr>"
        f"<tr><td><strong>Επιχείρηση/Γραφείο</strong></td><td>{safe['company']}</td></tr>"
        f"<tr><td><strong>Εύρος εργαζομένων</strong></td><td>{safe['employees']}</td></tr>"
        "</table>"
        f"<p style='white-space:pre-line;'>{safe['message']}</p>"
    )

    try:
        send_email_message(CONTACT_TO_EMAIL, subject, text_body, html_body=html_body)
    except EmailNotConfigured:
        return jsonify({
            "success": False,
            "error": "Η αποστολή email δεν έχει ρυθμιστεί ακόμα.",
        }), 503
    except Exception:
        return jsonify({
            "success": False,
            "error": "Δεν ήταν δυνατή η αποστολή. Δοκιμάστε ξανά ή στείλτε email απευθείας.",
        }), 502

    return jsonify({"success": True, "message": "Το μήνυμα στάλθηκε. Θα επικοινωνήσουμε σύντομα."})
