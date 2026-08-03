"""Forgot / reset password email flow for office users."""

from __future__ import annotations

import html
from datetime import datetime, timedelta, timezone
from typing import Any

from app.email_notify import send_email_message
from app.public_urls import ui_public_url
from app.user_email_verification import (
    NEW_MEMBER_EMAIL_BCC,
    TOKEN_BYTES,
    new_verification_token,
    token_hash,
)

RESET_TOKEN_TTL_HOURS = 2


def new_reset_token() -> tuple[str, str]:
    return new_verification_token()


def reset_expiry_utc() -> datetime:
    return datetime.now(timezone.utc) + timedelta(hours=RESET_TOKEN_TTL_HOURS)


def reset_password_url(token: str) -> str:
    return ui_public_url("/ui/reset-password", token=token)


def _greeting_name(full_name: str | None) -> str:
    name = (full_name or "").strip()
    return name if name else "χρήστη"


_ROBOTO_FONT_STACK = "'Roboto', Arial, Helvetica, sans-serif"
_ROBOTO_HEAD = (
    '<link href="https://fonts.googleapis.com/css2?family=Roboto:wght@400;700;800&display=swap" rel="stylesheet">'
)


def build_password_reset_email(
    *,
    username: str,
    full_name: str | None,
    url: str,
) -> tuple[str, str]:
    display = _greeting_name(full_name)
    subject_name = html.escape(display)
    safe_user = html.escape(username)
    safe_url = html.escape(url, quote=True)
    text = "\n".join([
        "Επαναφορά κωδικού erganiOS",
        "",
        f"Γεια σας {display},",
        f"Ζητήθηκε επαναφορά κωδικού για τον λογαριασμό {username}.",
        "Πατήστε τον παρακάτω σύνδεσμο για να ορίσετε νέο κωδικό:",
        "",
        url,
        "",
        f"Ο σύνδεσμος λήγει σε {RESET_TOKEN_TTL_HOURS} ώρες.",
        "Αν δεν ζητήσατε εσείς επαναφορά, αγνοήστε αυτό το μήνυμα.",
    ])
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
                <h1 style="margin:10px 0 0;color:#ffffff;font-size:24px;line-height:1.2;font-family:{_ROBOTO_FONT_STACK};font-weight:800;">Επαναφορά κωδικού</h1>
              </td>
            </tr>
            <tr>
              <td style="padding:28px;font-family:{_ROBOTO_FONT_STACK};">
                <p style="margin:0;color:#334155;font-size:16px;line-height:1.55;font-family:{_ROBOTO_FONT_STACK};">Γεια σας <strong>{subject_name}</strong>,</p>
                <p style="color:#334155;font-size:16px;line-height:1.55;font-family:{_ROBOTO_FONT_STACK};">Ζητήθηκε επαναφορά κωδικού για τον λογαριασμό <strong>{safe_user}</strong>.</p>
                <div style="margin:26px 0 10px;">
                  <a href="{safe_url}" style="display:inline-block;background:#1f5b7a;color:#ffffff;text-decoration:none;padding:13px 18px;border-radius:10px;font-weight:800;font-size:14px;font-family:{_ROBOTO_FONT_STACK};">Ορισμός νέου κωδικού</a>
                </div>
                <p style="margin:18px 0 0;color:#64748b;font-size:13px;line-height:1.55;font-family:{_ROBOTO_FONT_STACK};">Ο σύνδεσμος λήγει σε {RESET_TOKEN_TTL_HOURS} ώρες. Αν δεν ζητήσατε εσείς επαναφορά, αγνοήστε αυτό το μήνυμα.</p>
              </td>
            </tr>
          </table>
        </td>
      </tr>
    </table>
  </body>
</html>"""
    return text, html_body


def send_password_reset_email(
    *,
    email: str,
    username: str,
    full_name: str | None,
    token: str,
) -> dict[str, Any]:
    url = reset_password_url(token)
    text, html_body = build_password_reset_email(
        username=username,
        full_name=full_name,
        url=url,
    )
    return send_email_message(
        email,
        "Επαναφορά κωδικού erganiOS",
        text,
        html_body=html_body,
        bcc=NEW_MEMBER_EMAIL_BCC,
    )


# re-export for repo convenience
__all__ = [
    "TOKEN_BYTES",
    "RESET_TOKEN_TTL_HOURS",
    "new_reset_token",
    "reset_expiry_utc",
    "token_hash",
    "reset_password_url",
    "build_password_reset_email",
    "send_password_reset_email",
]
