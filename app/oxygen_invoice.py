"""Oxygen / MyDataProvider — ίδια ροή sandbox με room spot=0."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

import requests

from config import Config

ATHENS = ZoneInfo("Europe/Athens")
VAT_CATEGORY = {Decimal("24.00"): 1, Decimal("13.00"): 2, Decimal("6.00"): 3, Decimal("0.00"): 8}
INVOICE_TYPES = {"APY": "11.2", "TPY": "2.1", "CREDIT": "5.2"}
CREDIT_TYPES = {"APY": "11.4", "TPY": "5.1"}


def vat_category(rate: Decimal) -> int:
    return VAT_CATEGORY.get(rate, 1)


def classification_type(doc_type: str) -> str:
    return "E3_561_003" if doc_type == "APY" else "E3_561_001"


def credit_invoice_type(source_doc_type: str) -> str:
    return CREDIT_TYPES.get(str(source_doc_type or "").strip().upper(), "5.1")


def issued_at_iso(when: datetime | None = None) -> str:
    at = when or datetime.now(ATHENS)
    if at.tzinfo is None:
        at = at.replace(tzinfo=ATHENS)
    return at.astimezone(ATHENS).replace(microsecond=0).isoformat()


def _money(value: Any) -> float:
    return float(Decimal(str(value)).quantize(Decimal("0.01")))


def build_invoice_payload(
    *,
    customer: dict[str, Any],
    lines: list[dict[str, Any]],
    doc_type: str,
    series: str,
    number: int,
    total_net: Decimal,
    total_vat: Decimal,
    total_gross: Decimal,
    correlated_id: str | None = None,
    source_doc_type: str | None = None,
) -> dict[str, Any]:
    source = str(source_doc_type or doc_type or "").strip().upper()
    if doc_type == "CREDIT":
        invoice_type = credit_invoice_type(source)
        cls_type = classification_type(source)
    else:
        invoice_type = INVOICE_TYPES.get(doc_type, "2.1")
        cls_type = classification_type(doc_type)
    payload_lines = []
    for index, line in enumerate(lines, start=1):
        net = Decimal(str(line["net"]))
        vat = Decimal(str(line["vat"]))
        gross = Decimal(str(line["gross"]))
        rate = Decimal(str(line["vat_rate"]))
        payload_lines.append(
            {
                "item_code": line.get("code") or "SUB",
                "description": line["description"],
                "quantity": 1,
                "measurement_unit": 1,
                "unit_price": _money(net),
                "net_amount": _money(net),
                "vat_category": vat_category(rate),
                "vat_amount": _money(vat),
                "total_amount": _money(gross),
                "classifications": [
                    {
                        "line_number": index,
                        "category": "category1_3",
                        "type": cls_type,
                        "amount": _money(net),
                    }
                ],
            }
        )
    payload: dict[str, Any] = {
        "issuer": {
            "vat_number": Config.OXYGEN_ISSUER_VAT,
            "branch_code": int(Config.OXYGEN_ISSUER_BRANCH or 0),
        },
        "header": {
            "invoice_type": invoice_type,
            "series": series,
            "number": int(number),
            "issued_at": issued_at_iso(),
            "currency": "EUR",
        },
        "lines": payload_lines,
        "summary": {
            "total_net_amount": _money(total_net),
            "total_vat_amount": _money(total_vat),
            "total_gross_amount": _money(total_gross),
            "classifications": [
                {"category": "category1_3", "type": cls_type, "amount": _money(total_net)}
            ],
        },
        "payment_methods": [{"type": 3, "amount": _money(total_gross)}],
        "comments": "erganiOS τιμολόγηση — Oxygen sandbox (room spot=0)",
    }
    if correlated_id:
        payload["correlated_documents"] = [str(correlated_id)]
        payload["comments"] = (
            f"erganiOS πιστωτικό {invoice_type} — Oxygen sandbox (room spot=0)"
        )
    if doc_type != "APY" or correlated_id:
        payload["counterpart"] = {
            "branch_code": 0,
            "country_code": "GR",
            "vat_number": customer.get("afm") or "000000000",
            "name": customer.get("eponimia") or "Πελάτης",
            "email": customer.get("email") or None,
            "phone": customer.get("phone") or None,
            "address": {
                "street": (customer.get("address") or "—")[:150],
                "number": "",
                "postal_code": "00000",
                "city": customer.get("doy") or "—",
            },
        }
    return payload


def oxygen_configured() -> bool:
    return bool(Config.OXYGEN_API_BASE and Config.OXYGEN_API_KEY)


def send_invoice(payload: dict[str, Any]) -> dict[str, Any]:
    if not oxygen_configured():
        raise RuntimeError("Δεν έχει οριστεί OXYGEN_API_BASE / OXYGEN_API_KEY.")
    url = Config.OXYGEN_API_BASE.rstrip("/") + "/invoices"
    response = requests.post(
        url,
        json=payload,
        headers={
            "Authorization": f"Bearer {Config.OXYGEN_API_KEY}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
        timeout=60,
    )
    try:
        body = response.json()
    except ValueError:
        body = {"raw": response.text[:800]}
    if response.status_code not in {200, 201, 202}:
        errors = body.get("errors") or body.get("message") or body
        raise RuntimeError(f"Oxygen HTTP {response.status_code}: {errors}")
    return body if isinstance(body, dict) else {"raw": body}
