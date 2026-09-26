"""Συμπλήρωση ιδιωτικού συμφωνητικού ανάληψης ευθύνης ΕΡΓΑΝΗ."""

from __future__ import annotations

import io
import re
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape
from zoneinfo import ZoneInfo

from app.billing_invoice_form import issuer_profile
from config import Config

TEMPLATE_PATH = (
    Path(__file__).resolve().parent / "private" / "billing" / "symfonitiko_analipsis_efthynis.docx"
)
OFFER_TEMPLATE_PATH = (
    Path(__file__).resolve().parent / "private" / "billing" / "prosfora_erganios.docx"
)
_ELLIPSIS = "\u2026"
_ATHENS = ZoneInfo("Europe/Athens")

_BLANK_ORDER = (
    ("__________", "place"),
    ("___/___/____", "date"),
    ("________________________", "provider_name"),
    ("__________", "provider_afm"),
    ("______________________", "provider_address"),
    ("______________________", "provider_rep"),
    ("________________________", "employer_name"),
    ("__________", "employer_afm"),
    ("______________________", "employer_address"),
    ("______________________", "employer_rep"),
)


def issuer_city(address: str | None = None) -> str:
    configured = str(getattr(Config, "BILLING_ISSUER_CITY", "") or "").strip()
    if configured:
        return configured
    tail = str(address or "").split(",")[-1].strip()
    tail = re.sub(r"^\d{3,5}\s*", "", tail).strip(" .")
    return tail or "Αθήνα"


def _xml_text(value: Any, fallback: str = "—") -> str:
    text = " ".join(str(value or "").split()).strip() or fallback
    return escape(text)


def _fill_values(customer: dict[str, Any]) -> dict[str, str]:
    issuer = issuer_profile()
    today = datetime.now(_ATHENS).strftime("%d/%m/%Y")
    provider_rep = (
        str(getattr(Config, "BILLING_ISSUER_REPRESENTATIVE", "") or "").strip()
        or "νόμιμο εκπρόσωπο"
    )
    return {
        "place": _xml_text(issuer_city(str(issuer.get("address") or ""))),
        "date": _xml_text(today),
        "provider_name": _xml_text(issuer.get("name")),
        "provider_afm": _xml_text(issuer.get("afm")),
        "provider_address": _xml_text(issuer.get("address")),
        "provider_rep": _xml_text(provider_rep),
        "employer_name": _xml_text(customer.get("eponimia")),
        "employer_afm": _xml_text(customer.get("afm")),
        "employer_address": _xml_text(customer.get("address")),
        "employer_rep": _xml_text(customer.get("representative")),
    }


def _fill_docx(template: Path, replacements: list[tuple[str, str]], missing: str) -> bytes:
    if not template.is_file():
        raise FileNotFoundError(missing)
    source = template.read_bytes()
    out = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(source)) as zin, zipfile.ZipFile(out, "w") as zout:
        for item in zin.infolist():
            data = zin.read(item.filename)
            if item.filename == "word/document.xml":
                xml = data.decode("utf-8")
                for blank, value in replacements:
                    xml = xml.replace(blank, value, 1)
                data = xml.encode("utf-8")
            zout.writestr(item, data)
    return out.getvalue()


def fill_agreement_docx(customer: dict[str, Any]) -> bytes:
    values = _fill_values(customer)
    return _fill_docx(
        TEMPLATE_PATH,
        [(blank, values[key]) for blank, key in _BLANK_ORDER],
        "Δεν βρέθηκε το πρότυπο συμφωνητικού.",
    )


def fill_offer_docx(customer: dict[str, Any]) -> bytes:
    today = datetime.now(_ATHENS).strftime("%d/%m/%Y")
    return _fill_docx(
        OFFER_TEMPLATE_PATH,
        [
            (_ELLIPSIS * 7, _xml_text(customer.get("eponimia"))),
            (_ELLIPSIS * 6, _xml_text(today)),
        ],
        "Δεν βρέθηκε το πρότυπο προσφοράς.",
    )


def customer_for_agreement(data: dict[str, Any]) -> dict[str, Any]:
    from app.repo_billing import afm_is_valid, normalize_afm

    eponimia = str(data.get("eponimia") or "").strip()
    afm = normalize_afm(data.get("afm"))
    representative = str(data.get("representative") or "").strip()
    if not eponimia:
        raise ValueError("Η επωνυμία είναι υποχρεωτική για το συμφωνητικό.")
    if not afm_is_valid(afm):
        raise ValueError("Μη έγκυρο ΑΦΜ για το συμφωνητικό.")
    if not representative:
        raise ValueError("Απαιτείται το όνομα του εκπροσώπου")
    return {
        "eponimia": eponimia[:200],
        "afm": afm,
        "address": str(data.get("address") or "").strip()[:400],
        "representative": representative[:200],
    }


def _safe_customer_slug(customer: dict[str, Any]) -> str:
    raw = str(customer.get("eponimia") or "πελάτης")
    safe = re.sub(r"[^\w\s\-Α-ω]+", "", raw, flags=re.UNICODE).strip()
    return re.sub(r"\s+", "_", safe)[:80] or "pelatis"


def agreement_filename(customer: dict[str, Any]) -> str:
    return f"Symfonitiko_Analipsis_Efthynis_{_safe_customer_slug(customer)}.docx"


def offer_filename(customer: dict[str, Any]) -> str:
    return f"Prosfora_erganiOS_{_safe_customer_slug(customer)}.docx"
