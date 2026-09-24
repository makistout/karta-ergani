"""Στοιχεία εκδότη και όψη εντύπου τιμολογίου προς τον πελάτη."""

from __future__ import annotations

from typing import Any

from app.billing_qr import qr_svg_data_uri
from config import Config

DOC_TITLES = {
    "APY": "Απόδειξη Παροχής Υπηρεσιών",
    "TPY": "Τιμολόγιο Παροχής Υπηρεσιών",
    "CREDIT": "Πιστωτικό Τιμολόγιο",
}


def issuer_profile() -> dict[str, Any]:
    return {
        "name": Config.BILLING_ISSUER_NAME,
        "afm": Config.BILLING_ISSUER_AFM,
        "doy": Config.BILLING_ISSUER_DOY,
        "address": Config.BILLING_ISSUER_ADDRESS,
        "gemh": Config.BILLING_ISSUER_GEMH,
        "email": Config.BILLING_ISSUER_EMAIL,
        "phone": Config.BILLING_ISSUER_PHONE,
        "activity": Config.BILLING_ISSUER_ACTIVITY,
        "placeholder": True,
        "banks": [
            {"bank": "Εθνική Τράπεζα", "iban": Config.BILLING_BANK_NBG},
            {"bank": "Τράπεζα Πειραιώς", "iban": Config.BILLING_BANK_PIRAEUS},
            {"bank": "Eurobank", "iban": Config.BILLING_BANK_EUROBANK},
        ],
    }


def greek_date(raw: Any) -> str:
    text = str(raw or "").strip()[:10]
    parts = text.split("-")
    if len(parts) == 3 and len(parts[0]) == 4:
        return f"{parts[2]}/{parts[1]}/{parts[0]}"
    return str(raw or "").strip()


def _vat_percent(raw: Any) -> str:
    text = str(raw or "24").strip()
    if text.endswith(".00") or text.endswith(",00"):
        text = text[:-3]
    return text or "24"


def invoice_view(document_id: int) -> dict[str, Any] | None:
    from app.repo_billing import DOC_TYPE_LABELS, format_euro, get_document

    doc = get_document(int(document_id))
    if not doc:
        return None
    lines = []
    vat_rates: list[str] = []
    for index, line in enumerate(doc.get("lines") or [], start=1):
        vat_pct = _vat_percent(line.get("vat_rate"))
        vat_rates.append(vat_pct)
        lines.append(
            {
                **line,
                "aa": index,
                "net_fmt": format_euro(line.get("net")),
                "vat_fmt": format_euro(line.get("vat")),
                "gross_fmt": format_euro(line.get("gross")),
                "vat_pct": vat_pct,
            }
        )
    series = str(doc.get("series") or "1")
    number = doc.get("number") or ""
    doc_type = str(doc.get("doc_type") or "TPY")
    if doc_type == "CREDIT":
        number_label = f"{series}{number}" if number != "" else series
    else:
        number_label = f"{doc_type}{number}" if number != "" else f"{doc_type}{series}"
    vat_label = vat_rates[0] if vat_rates and len(set(vat_rates)) == 1 else "24"
    qr_payload = (
        str(doc.get("qr_url") or "").strip()
        or str(doc.get("icode") or "").strip()
        or str(doc.get("uid") or "").strip()
        or str(doc.get("form_url") or "").strip()
    )
    return {
        "doc": doc,
        "customer": doc.get("customer") or {},
        "issuer": issuer_profile(),
        "lines": lines,
        "title": DOC_TITLES.get(doc_type, "Παραστατικό"),
        "doc_type_label": DOC_TYPE_LABELS.get(doc_type, doc_type),
        "number_label": number_label,
        "issued_on": greek_date(doc.get("issued_on")),
        "settlement": "ΣΥΜΨΗΦΙΣΜΟΣ" if doc_type == "CREDIT" else "ΕΠΙ ΠΙΣΤΩΣΕΙ",
        "related_label": doc.get("related_label"),
        "vat_label": vat_label,
        "total_net": format_euro(doc.get("total_net")),
        "total_vat": format_euro(doc.get("total_vat")),
        "total_gross": format_euro(doc.get("total_gross")),
        "qr_data_url": qr_svg_data_uri(qr_payload),
        "provider_name": Config.BILLING_PROVIDER_NAME,
        "provider_url": Config.BILLING_PROVIDER_URL,
        "remarks_intro": (
            "Παρακαλούμε να εξοφλήσετε το παρόν, κατά τους συμφωνηθέντες "
            "όρους πίστωσης, με κατάθεση σε έναν από τους λογαριασμούς:"
        ),
        "placeholder_note": (
            "Τα στοιχεία εκδότη, ΓΕΜΗ και οι τραπεζικοί λογαριασμοί είναι ενδεικτικά "
            "μέχρι να οριστούν τα πραγματικά (BILLING_ISSUER_* / BILLING_BANK_*)."
        ),
    }
