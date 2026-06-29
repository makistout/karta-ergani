"""Αποστολή email ειδοποιήσεων ληπτών καταστήματος."""

from __future__ import annotations

import html
import os
import smtplib
from email.message import EmailMessage
from pathlib import Path
from typing import Any

from dotenv import load_dotenv


class EmailNotConfigured(Exception):
    pass


def _smtp_settings() -> dict[str, Any]:
    load_dotenv(Path(__file__).resolve().parents[1] / ".env", override=True)
    host = (os.environ.get("SMTP_HOST") or "").strip()
    from_email = (
        (os.environ.get("SMTP_FROM_EMAIL") or os.environ.get("SMTP_USERNAME") or "")
        .strip()
    )
    if not host or not from_email:
        raise EmailNotConfigured(
            "Λείπουν SMTP_HOST/SMTP_FROM_EMAIL στο .env για αποστολή email."
        )
    port_raw = (os.environ.get("SMTP_PORT") or "587").strip() or "587"
    use_tls_raw = (os.environ.get("SMTP_USE_TLS") or "1").strip().lower()
    use_ssl_raw = (os.environ.get("SMTP_USE_SSL") or "0").strip().lower()
    return {
        "host": host,
        "port": int(port_raw),
        "username": (os.environ.get("SMTP_USERNAME") or "").strip(),
        "password": os.environ.get("SMTP_PASSWORD") or "",
        "from_email": from_email,
        "from_name": (os.environ.get("SMTP_FROM_NAME") or "erganiOS").strip(),
        "use_tls": use_tls_raw in ("1", "true", "yes", "on"),
        "use_ssl": use_ssl_raw in ("1", "true", "yes", "on"),
    }


def _sender_header(settings: dict[str, Any]) -> str:
    name = str(settings.get("from_name") or "").strip()
    email = str(settings.get("from_email") or "").strip()
    if not name:
        return email
    safe_name = name.replace('"', "'")
    return f'"{safe_name}" <{email}>'


def send_email_message(
    to_email: str,
    subject: str,
    text_body: str,
    *,
    html_body: str | None = None,
) -> dict[str, Any]:
    settings = _smtp_settings()
    to_addr = str(to_email or "").strip()
    if not to_addr:
        raise ValueError("Λείπει email παραλήπτη")

    msg = EmailMessage()
    msg["From"] = _sender_header(settings)
    msg["To"] = to_addr
    msg["Subject"] = str(subject or "erganiOS")
    msg.set_content(text_body or "")
    if html_body:
        msg.add_alternative(html_body, subtype="html")

    if settings["use_ssl"]:
        smtp: smtplib.SMTP = smtplib.SMTP_SSL(settings["host"], settings["port"], timeout=30)
    else:
        smtp = smtplib.SMTP(settings["host"], settings["port"], timeout=30)
    with smtp:
        if settings["use_tls"] and not settings["use_ssl"]:
            smtp.starttls()
        if settings["username"]:
            smtp.login(settings["username"], settings["password"])
        smtp.send_message(msg)
    return {"ok": True, "to": to_addr}


def _pill(label: str, value: str | None) -> str:
    safe_label = html.escape(label)
    safe_value = html.escape(str(value or "—"))
    return (
        '<tr>'
        f'<td style="padding:10px 0;color:#64748b;font-size:13px;">{safe_label}</td>'
        f'<td style="padding:10px 0;color:#0f172a;font-size:14px;font-weight:700;text-align:right;">{safe_value}</td>'
        '</tr>'
    )


def build_notification_email(
    *,
    title: str,
    preheader: str,
    store_name: str | None = None,
    employee_name: str | None = None,
    employee_afm: str | None = None,
    work_date: str | None = None,
    problem: str | None = None,
    details: list[tuple[str, str | None]] | None = None,
    action_url: str | None = None,
    action_label: str = "Άνοιγμα ενέργειας",
    footer_note: str | None = None,
) -> tuple[str, str]:
    """Επιστρέφει (plain_text, html) για transactional ειδοποίηση."""
    clean_title = str(title or "Ειδοποίηση erganiOS").strip()
    clean_preheader = str(preheader or "").strip()
    clean_store = str(store_name or "").strip()
    clean_employee = str(employee_name or employee_afm or "—").strip()
    clean_problem = str(problem or "").strip()
    rows = [
        ("Κατάστημα", clean_store or "—"),
        ("Εργαζόμενος", clean_employee),
        ("ΑΦΜ", employee_afm or "—"),
        ("Ημερομηνία", work_date or "—"),
    ]
    rows.extend(details or [])

    plain_lines = [clean_title]
    if clean_store:
        plain_lines.append(f"Κατάστημα: {clean_store}")
    if clean_problem:
        plain_lines.append(clean_problem)
    plain_lines.extend(f"{label}: {value or '—'}" for label, value in rows[1:])
    if action_url:
        plain_lines.append("")
        plain_lines.append(f"{action_label}: {action_url}")
    if footer_note:
        plain_lines.append("")
        plain_lines.append(str(footer_note))
    plain_text = "\n".join(plain_lines)

    escaped_rows = "".join(_pill(label, value) for label, value in rows)
    button = ""
    if action_url:
        safe_url = html.escape(action_url, quote=True)
        safe_label = html.escape(action_label)
        button = (
            '<div style="margin:26px 0 8px;">'
            f'<a href="{safe_url}" style="display:inline-block;background:#2563eb;color:#ffffff;'
            'text-decoration:none;padding:13px 18px;border-radius:12px;font-weight:800;'
            'font-size:14px;box-shadow:0 10px 20px rgba(37,99,235,.22);">'
            f'{safe_label}</a>'
            '</div>'
        )

    note_html = ""
    if footer_note:
        note_html = (
            '<p style="margin:20px 0 0;color:#64748b;font-size:13px;line-height:1.55;">'
            f'{html.escape(str(footer_note))}</p>'
        )

    badge = html.escape(clean_store or "erganiOS")
    problem_html = (
        f'<p style="margin:14px 0 0;color:#334155;font-size:16px;line-height:1.55;">'
        f'{html.escape(clean_problem)}</p>'
        if clean_problem
        else ""
    )
    html_body = f"""<!doctype html>
<html lang="el">
  <body style="margin:0;background:#f1f5f9;font-family:Arial,Helvetica,sans-serif;color:#0f172a;">
    <span style="display:none!important;visibility:hidden;opacity:0;color:transparent;height:0;width:0;overflow:hidden;">
      {html.escape(clean_preheader)}
    </span>
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f1f5f9;padding:28px 12px;">
      <tr>
        <td align="center">
          <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:620px;background:#ffffff;border-radius:22px;overflow:hidden;border:1px solid #e2e8f0;box-shadow:0 18px 45px rgba(15,23,42,.08);">
            <tr>
              <td style="padding:26px 28px;background:linear-gradient(135deg,#0f172a,#1d4ed8);">
                <div style="color:#bfdbfe;font-size:12px;font-weight:800;letter-spacing:.04em;">erganiOS</div>
                <h1 style="margin:10px 0 0;color:#ffffff;font-size:24px;line-height:1.2;">{html.escape(clean_title)}</h1>
                <div style="display:inline-block;margin-top:14px;padding:7px 11px;border-radius:999px;background:rgba(255,255,255,.12);color:#e0f2fe;font-size:13px;">{badge}</div>
              </td>
            </tr>
            <tr>
              <td style="padding:28px;">
                {problem_html}
                <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-top:22px;border-top:1px solid #e2e8f0;border-bottom:1px solid #e2e8f0;">
                  {escaped_rows}
                </table>
                {button}
                {note_html}
              </td>
            </tr>
            <tr>
              <td style="padding:18px 28px;background:#f8fafc;color:#64748b;font-size:12px;line-height:1.5;">
                Αυτό το μήνυμα στάλθηκε αυτόματα από το erganiOS. Αν δεν αναγνωρίζετε την ειδοποίηση,
                επικοινωνήστε με τον διαχειριστή του καταστήματος.
              </td>
            </tr>
          </table>
        </td>
      </tr>
    </table>
  </body>
</html>"""
    return plain_text, html_body


def send_notification_email(
    to_email: str,
    subject: str,
    **template_kwargs: Any,
) -> dict[str, Any]:
    text_body, html_body = build_notification_email(**template_kwargs)
    return send_email_message(to_email, subject, text_body, html_body=html_body)
