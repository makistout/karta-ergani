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


def new_verification_token() -> tuple[str, str]:
    token = secrets.token_urlsafe(TOKEN_BYTES)
    return token, token_hash(token)


def token_hash(token: str) -> str:
    return hashlib.sha256(str(token or "").encode("utf-8")).hexdigest()


def expiry_utc() -> datetime:
    return datetime.now(timezone.utc) + timedelta(hours=TOKEN_TTL_HOURS)


def verification_url(token: str) -> str:
    return ui_public_url("/ui/verify-email", token=token)


def build_verification_email(*, username: str, full_name: str | None, url: str) -> tuple[str, str]:
    display = (full_name or username or "χρήστη").strip()
    subject_name = html.escape(display)
    safe_url = html.escape(url, quote=True)
    text = "\n".join([
        "Επιβεβαίωση email erganiOS",
        "",
        f"Γεια σας {display},",
        "Πατήστε τον παρακάτω σύνδεσμο για να επιβεβαιώσετε το email σας.",
        "",
        url,
        "",
        f"Ο σύνδεσμος λήγει σε {TOKEN_TTL_HOURS} ώρες.",
    ])
    html_body = f"""<!doctype html>
<html lang="el">
  <body style="margin:0;background:#f1f5f9;font-family:Arial,Helvetica,sans-serif;color:#0f172a;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f1f5f9;padding:28px 12px;">
      <tr>
        <td align="center">
          <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:620px;background:#ffffff;border-radius:18px;overflow:hidden;border:1px solid #e2e8f0;">
            <tr>
              <td style="padding:26px 28px;background:#1f5b7a;">
                <div style="color:#dbeafe;font-size:12px;font-weight:800;letter-spacing:.04em;">erganiOS</div>
                <h1 style="margin:10px 0 0;color:#ffffff;font-size:24px;line-height:1.2;">Επιβεβαίωση email</h1>
              </td>
            </tr>
            <tr>
              <td style="padding:28px;">
                <p style="margin:0;color:#334155;font-size:16px;line-height:1.55;">Γεια σας <strong>{subject_name}</strong>,</p>
                <p style="color:#334155;font-size:16px;line-height:1.55;">Πατήστε το κουμπί για να επιβεβαιώσετε το email σας στο erganiOS.</p>
                <div style="margin:26px 0 10px;">
                  <a href="{safe_url}" style="display:inline-block;background:#1f5b7a;color:#ffffff;text-decoration:none;padding:13px 18px;border-radius:10px;font-weight:800;font-size:14px;">Επιβεβαίωση email</a>
                </div>
                <p style="margin:18px 0 0;color:#64748b;font-size:13px;line-height:1.55;">Ο σύνδεσμος λήγει σε {TOKEN_TTL_HOURS} ώρες.</p>
              </td>
            </tr>
          </table>
        </td>
      </tr>
    </table>
  </body>
</html>"""
    return text, html_body


def send_verification_email(*, email: str, username: str, full_name: str | None, token: str) -> dict[str, Any]:
    url = verification_url(token)
    text, html_body = build_verification_email(
        username=username,
        full_name=full_name,
        url=url,
    )
    return send_email_message(
        email,
        "Επιβεβαίωση email erganiOS",
        text,
        html_body=html_body,
    )
