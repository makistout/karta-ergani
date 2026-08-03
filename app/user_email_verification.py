"""Email verification flow for office users."""

from __future__ import annotations

import hashlib
import html
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from app.email_notify import send_email_message
from app.public_urls import ui_public_url

TOKEN_BYTES = 32
TOKEN_TTL_HOURS = 48
NEW_MEMBER_EMAIL_BCC = "info@erganios.gr"
_TEMP_PASSWORD_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789"


def new_temporary_password(length: int = 12) -> str:
    """Αναγνώσιμος προσωρινός κωδικός για welcome/resend email."""
    n = max(8, min(int(length or 12), 32))
    return "".join(secrets.choice(_TEMP_PASSWORD_ALPHABET) for _ in range(n))


def new_verification_token() -> tuple[str, str]:
    token = secrets.token_urlsafe(TOKEN_BYTES)
    return token, token_hash(token)


def token_hash(token: str) -> str:
    return hashlib.sha256(str(token or "").encode("utf-8")).hexdigest()


def expiry_utc() -> datetime:
    return datetime.now(timezone.utc) + timedelta(hours=TOKEN_TTL_HOURS)


def verification_url(token: str) -> str:
    return ui_public_url("/ui/verify-email", token=token)


def _greeting_name(full_name: str | None, username: str) -> str:
    """Ονοματεπώνυμο για χαιρετισμό — όχι username."""
    name = (full_name or "").strip()
    if name:
        return name
    return "χρήστη"


_ROBOTO_FONT_STACK = "'Roboto', Arial, Helvetica, sans-serif"
_ROBOTO_HEAD = (
    '<link href="https://fonts.googleapis.com/css2?family=Roboto:wght@400;700;800&display=swap" rel="stylesheet">'
)


def build_verification_email(
    *,
    username: str,
    full_name: str | None,
    url: str,
    temporary_password: str | None = None,
) -> tuple[str, str]:
    display = _greeting_name(full_name, username)
    subject_name = html.escape(display)
    safe_user = html.escape(username)
    safe_url = html.escape(url, quote=True)
    temp_pwd = (temporary_password or "").strip()
    safe_pwd = html.escape(temp_pwd) if temp_pwd else ""

    cred_lines = [f"Username: {username}"]
    if temp_pwd:
        cred_lines.append(f"Προσωρινός κωδικός: {temp_pwd}")
    step2 = (
        f"2) Συνδεθείτε με προσωρινό κωδικό: {temp_pwd}"
        if temp_pwd
        else "2) Συνδεθείτε με τον προσωρινό κωδικό που σας έδωσε ο διαχειριστής."
    )
    text = "\n".join([
        "Καλωσήρθατε στο erganiOS",
        "",
        f"Γεια σας {display},",
        "Δημιουργήθηκε λογαριασμός στο erganiOS.",
        *cred_lines,
        "",
        "1) Πατήστε τον παρακάτω σύνδεσμο για να επιβεβαιώσετε το email σας.",
        step2,
        "3) Στην πρώτη σύνδεση θα σας ζητηθεί αλλαγή κωδικού και αποδοχή όρων χρήσης.",
        "",
        url,
        "",
        f"Ο σύνδεσμος λήγει σε {TOKEN_TTL_HOURS} ώρες.",
    ])

    if temp_pwd:
        cred_html = (
            f'<p style="margin:14px 0;padding:14px 16px;background:#f0f9ff;border:2px solid #1f5b7a;'
            f'border-radius:10px;color:#0f172a;font-size:15px;line-height:1.7;font-family:{_ROBOTO_FONT_STACK};">'
            f'Username: <strong>{safe_user}</strong><br>'
            f'Προσωρινός κωδικός: '
            f'<strong style="font-size:18px;letter-spacing:.04em;font-family:Consolas,Monaco,monospace;">'
            f'{safe_pwd}</strong>'
            f"</p>"
        )
        step2_html = (
            f'Συνδεθείτε με προσωρινό κωδικό: '
            f'<strong style="font-family:Consolas,Monaco,monospace;">{safe_pwd}</strong>'
        )
        intro_html = (
            f'<p style="margin:0;color:#334155;font-size:16px;line-height:1.55;font-family:{_ROBOTO_FONT_STACK};">'
            f'Γεια σας <strong>{subject_name}</strong>,</p>'
            f'<p style="color:#334155;font-size:16px;line-height:1.55;font-family:{_ROBOTO_FONT_STACK};">'
            f'Δημιουργήθηκε λογαριασμός στο erganiOS. Τα στοιχεία σύνδεσης:</p>'
        )
    else:
        cred_html = (
            f'<p style="color:#334155;font-size:16px;line-height:1.55;font-family:{_ROBOTO_FONT_STACK};">'
            f'Δημιουργήθηκε λογαριασμός στο erganiOS με username <strong>{safe_user}</strong>.</p>'
        )
        step2_html = "Συνδεθείτε με τον προσωρινό κωδικό που σας έδωσε ο διαχειριστής."
        intro_html = (
            f'<p style="margin:0;color:#334155;font-size:16px;line-height:1.55;font-family:{_ROBOTO_FONT_STACK};">'
            f'Γεια σας <strong>{subject_name}</strong>,</p>'
        )
    html_body = f"""<!doctype html>
<html lang="el">
  <head>
    <meta charset="utf-8">
    {_ROBOTO_HEAD}
  </head>
  <body style="margin:0;background:#f1f5f9;font-family:{_ROBOTO_FONT_STACK};color:#0f172a;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f1f5f9;padding:28px 12px;font-family:{_ROBOTO_FONT_STACK};">
      <tr>
        <td align="center">
          <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:620px;background:#ffffff;border-radius:18px;overflow:hidden;border:1px solid #e2e8f0;font-family:{_ROBOTO_FONT_STACK};">
            <tr>
              <td style="padding:26px 28px;background:#1f5b7a;font-family:{_ROBOTO_FONT_STACK};">
                <div style="color:#dbeafe;font-size:12px;font-weight:800;letter-spacing:.04em;">erganiOS</div>
                <h1 style="margin:10px 0 0;color:#ffffff;font-size:24px;line-height:1.2;font-family:{_ROBOTO_FONT_STACK};font-weight:800;">Καλωσήρθατε</h1>
              </td>
            </tr>
            <tr>
              <td style="padding:28px;font-family:{_ROBOTO_FONT_STACK};">
                {intro_html}
                {cred_html}
                <ol style="color:#334155;font-size:15px;line-height:1.55;padding-left:1.2rem;font-family:{_ROBOTO_FONT_STACK};">
                  <li>Επιβεβαιώστε το email σας με το κουμπί παρακάτω.</li>
                  <li>{step2_html}</li>
                  <li>Στην πρώτη σύνδεση θα σας ζητηθεί <strong>αλλαγή κωδικού</strong> και <strong>αποδοχή όρων χρήσης</strong>.</li>
                </ol>
                <div style="margin:26px 0 10px;">
                  <a href="{safe_url}" style="display:inline-block;background:#1f5b7a;color:#ffffff;text-decoration:none;padding:13px 18px;border-radius:10px;font-weight:800;font-size:14px;font-family:{_ROBOTO_FONT_STACK};">Επιβεβαίωση email</a>
                </div>
                <p style="margin:18px 0 0;color:#64748b;font-size:13px;line-height:1.55;font-family:{_ROBOTO_FONT_STACK};">Ο σύνδεσμος λήγει σε {TOKEN_TTL_HOURS} ώρες.</p>
              </td>
            </tr>
          </table>
        </td>
      </tr>
    </table>
  </body>
</html>"""
    return text, html_body


def send_verification_email(
    *,
    email: str,
    username: str,
    full_name: str | None,
    token: str,
    temporary_password: str | None = None,
) -> dict[str, Any]:
    url = verification_url(token)
    text, html_body = build_verification_email(
        username=username,
        full_name=full_name,
        url=url,
        temporary_password=temporary_password,
    )
    return send_email_message(
        email,
        "Καλωσήρθατε στο erganiOS — επιβεβαίωση email",
        text,
        html_body=html_body,
        bcc=NEW_MEMBER_EMAIL_BCC,
    )
