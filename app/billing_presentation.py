"""Αποστολή παρουσίασης erganiOS στον πελάτη."""

from __future__ import annotations

import html
import re
from pathlib import Path
from typing import Any

from app.email_notify import send_email_message
from config import Config

PRESENTATION_DIR = Path(__file__).resolve().parent / "private" / "billing"
PRESENTATION_CATALOG = (
    {
        "key": "apologistiko",
        "filename": "erganiOS_apologistiko_orometrisi.pdf",
        "title": "Απολογιστικό & Ωρομέτρηση",
    },
    {
        "key": "ai-agent",
        "filename": "erganiOS_AI-Agent.pdf",
        "title": "AI Agent",
    },
)
PRESENTATION_FILES = tuple(PRESENTATION_DIR / item["filename"] for item in PRESENTATION_CATALOG)
PRESENTATION_BCC = "info@erganios.gr"
PRESENTATION_SUBJECT = "Παρουσίαση υπηρεσίας erganiOS"
_EMAIL_RE = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
_PLACEHOLDER_PHONES = {"", "χχχχχχχ", "210 0000 000", "2100000000"}


def presentation_items() -> list[dict[str, str]]:
    return [
        {
            "key": item["key"],
            "title": item["title"],
            "filename": item["filename"],
            "url": f"/api/billing/presentation/files/{item['key']}",
        }
        for item in PRESENTATION_CATALOG
    ]


def presentation_file(key: str) -> Path:
    wanted = str(key or "").strip().casefold()
    for item in PRESENTATION_CATALOG:
        if item["key"] == wanted:
            path = PRESENTATION_DIR / item["filename"]
            if not path.is_file():
                raise FileNotFoundError(f"Δεν βρέθηκε το πρότυπο παρουσίασης: {path.name}")
            return path
    raise KeyError("Η παρουσίαση δεν βρέθηκε.")


def presentation_attachments() -> list[tuple[str, bytes]]:
    attachments: list[tuple[str, bytes]] = []
    for path in PRESENTATION_FILES:
        if not path.is_file():
            raise FileNotFoundError(f"Δεν βρέθηκε το πρότυπο παρουσίασης: {path.name}")
        attachments.append((path.name, path.read_bytes()))
    return attachments


def presentation_contact() -> dict[str, str]:
    phone = str(getattr(Config, "BILLING_CONTACT_PHONE", "") or "").strip()
    if not phone or phone.casefold() in _PLACEHOLDER_PHONES:
        agent = str(getattr(Config, "AI_AGENT_CONTACT_PHONE", "") or "").strip()
        if agent and agent.casefold() not in _PLACEHOLDER_PHONES:
            phone = agent
        else:
            issuer = str(getattr(Config, "BILLING_ISSUER_PHONE", "") or "").strip()
            phone = issuer if issuer.casefold() not in _PLACEHOLDER_PHONES else "6977392742"
    email = str(getattr(Config, "BILLING_ISSUER_EMAIL", "") or "info@erganios.gr").strip()
    site = str(getattr(Config, "PUBLIC_BASE_URL", "") or "https://erganios.gr").strip().rstrip("/")
    name = str(getattr(Config, "BILLING_CONTACT_NAME", "") or "").strip() or "erganiOS"
    return {
        "name": name,
        "phone": phone,
        "email": email or "info@erganios.gr",
        "site": site or "https://erganios.gr",
    }


def customer_for_presentation(data: dict[str, Any]) -> dict[str, Any]:
    email = str(data.get("email") or "").strip()
    if not email:
        raise ValueError("Απαιτείται το email του πελάτη")
    if not _EMAIL_RE.match(email):
        raise ValueError("Μη έγκυρο email πελάτη")
    return {
        "eponimia": str(data.get("eponimia") or "").strip()[:200],
        "representative": str(data.get("representative") or "").strip()[:200],
        "email": email[:180],
    }


def build_presentation_email(customer: dict[str, Any]) -> tuple[str, str]:
    contact = presentation_contact()
    representative = str(customer.get("representative") or "").strip()
    eponimia = str(customer.get("eponimia") or "").strip()
    if representative:
        greeting = f"Αξιότιμε/η κ. {representative},"
    elif eponimia:
        greeting = f"Αξιότιμοι κύριοι,"
    else:
        greeting = "Αξιότιμε/η,"
    intro = (
        "Παρακαλώ βρείτε επισυναπτόμενη μια συνοπτική παρουσίαση της υπηρεσίας "
        "erganiOS και παραμένουμε στη διάθεσή σας για οποιαδήποτε διευκρίνιση."
    )
    closing = (
        f"Με εκτίμηση,\n"
        f"{contact['name']}\n"
        f"\n"
        f"Τηλ.: {contact['phone']}\n"
        f"Email: {contact['email']}\n"
        f"Web: {contact['site']}"
    )
    text_body = f"{greeting}\n\n{intro}\n\n{closing}\n"
    safe = {key: html.escape(value) for key, value in {
        "greeting": greeting,
        "intro": intro,
        "name": contact["name"],
        "phone": contact["phone"],
        "email": contact["email"],
        "site": contact["site"],
    }.items()}
    html_body = f"""<!doctype html>
<html lang="el">
  <body style="margin:0;background:#f1f5f9;font-family:Arial,Helvetica,sans-serif;color:#0f172a;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f1f5f9;padding:28px 12px;">
      <tr>
        <td align="center">
          <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:620px;background:#ffffff;border-radius:22px;overflow:hidden;border:1px solid #e2e8f0;">
            <tr>
              <td style="padding:26px 28px;background:#0f172a;">
                <div style="color:#bfdbfe;font-size:12px;font-weight:800;letter-spacing:.04em;">erganiOS</div>
                <h1 style="margin:10px 0 0;color:#ffffff;font-size:22px;line-height:1.25;">Παρουσίαση υπηρεσίας</h1>
              </td>
            </tr>
            <tr>
              <td style="padding:28px;font-size:15px;line-height:1.6;">
                <p style="margin:0 0 16px;">{safe['greeting']}</p>
                <p style="margin:0 0 22px;">{safe['intro']}</p>
                <p style="margin:0 0 4px;">Με εκτίμηση,</p>
                <p style="margin:0 0 18px;font-weight:700;">{safe['name']}</p>
                <p style="margin:0;color:#475569;font-size:14px;line-height:1.7;">
                  Τηλ.: {safe['phone']}<br>
                  Email: <a href="mailto:{safe['email']}" style="color:#1d4ed8;">{safe['email']}</a><br>
                  Web: <a href="{safe['site']}" style="color:#1d4ed8;">{safe['site']}</a>
                </p>
              </td>
            </tr>
          </table>
        </td>
      </tr>
    </table>
  </body>
</html>"""
    return text_body, html_body


def send_presentation(customer: dict[str, Any]) -> dict[str, Any]:
    recipient = customer_for_presentation(customer)
    text_body, html_body = build_presentation_email(recipient)
    result = send_email_message(
        recipient["email"],
        PRESENTATION_SUBJECT,
        text_body,
        html_body=html_body,
        bcc=PRESENTATION_BCC,
        attachments=presentation_attachments(),
    )
    result["attachments"] = [path.name for path in PRESENTATION_FILES]
    return result
