from decimal import Decimal

from app.access_control import permission_for_path
from app.oxygen_invoice import (
    build_invoice_payload,
    classification_type,
    credit_invoice_type,
    vat_category,
)
from app.billing_agreement import (
    agreement_filename,
    customer_for_agreement,
    fill_agreement_docx,
    fill_offer_docx,
    issuer_city,
    offer_filename,
)
from app.billing_invoice_form import greek_date, issuer_profile
from app.billing_presentation import (
    PRESENTATION_BCC,
    PRESENTATION_FILES,
    PRESENTATION_SUBJECT,
    build_presentation_email,
    customer_for_presentation,
    presentation_attachments,
    presentation_contact,
    presentation_file,
    presentation_items,
    send_presentation,
)
from app.billing_qr import qr_svg_data_uri
from app.repo_billing import (
    afm_is_valid,
    format_euro,
    money,
    normalize_afm,
    normalize_plan_name,
    plan_issue_items,
    vat_amount,
)


def test_afm_checksum():
    assert normalize_afm(" 123456783 ") == "123456783"
    assert afm_is_valid("123456783") is True
    assert afm_is_valid("123456789") is False
    assert afm_is_valid("123") is False


def test_plan_issue_items_from_ids_and_plans():
    from_ids = plan_issue_items({"plan_ids": ["3", 4, "x"], "starts_on": "2026-09-01"})
    assert from_ids == [
        {"plan_id": 3, "starts_on": "2026-09-01"},
        {"plan_id": 4, "starts_on": "2026-09-01"},
    ]
    from_plans = plan_issue_items({
        "plans": [{"plan_id": 7, "amount_net": "10.00"}, {"plan_id": 0}],
        "starts_on": "2026-09-24",
    })
    assert from_plans == [{"plan_id": 7, "starts_on": "2026-09-24", "amount_net": "10.00"}]


def test_plan_names_normalize_for_uniqueness():
    assert normalize_plan_name("  ErganiOS + AI  ") == normalize_plan_name("erganios + ai")
    assert normalize_plan_name("Α") != normalize_plan_name("Β")


def test_money_and_vat():
    assert str(money("10.1")) == "10.10"
    assert str(vat_amount(money("100"), money("24"))) == "24.00"


def test_billing_paths_are_super_admin_permission():
    assert permission_for_path("/ui/billing", "GET") == "billing.manage"
    assert permission_for_path("/ui/billing/customer", "GET") == "billing.manage"
    assert permission_for_path("/ui/billing/subscriptions", "GET") == "billing.manage"
    assert permission_for_path("/ui/billing/invoices", "GET") == "billing.manage"
    assert permission_for_path("/ui/billing/invoice/12", "GET") == "billing.manage"
    assert permission_for_path("/ui/billing/presentations", "GET") == "billing.manage"
    assert permission_for_path("/api/billing/customers", "GET") == "billing.manage"
    assert permission_for_path("/api/billing/documents/issue", "POST") == "billing.manage"
    assert permission_for_path("/api/billing/documents/1/credit", "POST") == "billing.manage"
    assert permission_for_path("/api/billing/plans/1/duplicate", "POST") == "billing.manage"
    assert permission_for_path("/api/billing/agreement", "POST") == "billing.manage"
    assert permission_for_path("/api/billing/offer", "POST") == "billing.manage"
    assert permission_for_path("/api/billing/presentation", "POST") == "billing.manage"
    assert permission_for_path("/api/billing/presentation/files/apologistiko", "GET") == "billing.manage"


def test_agreement_fills_customer_and_issuer():
    import zipfile
    from io import BytesIO

    assert issuer_city("Λαχανά 17, 12131 Περιστέρι") == "Περιστέρι"
    customer = customer_for_agreement({
        "eponimia": "ΑΙΣΤΟΟΥ ΥΠΗΡΕΣΙΕΣ ΙΝΤΕΡΝΕΤ Μ.ΙΚΕ",
        "afm": "998031206",
        "address": "ΛΑΧΑΝΑ 17 ΠΕΡΙΣΤΕΡΙ ΤΚ 12131",
        "representative": "Μάκης Τουτουδάκης",
    })
    content = fill_agreement_docx(customer)
    xml = zipfile.ZipFile(BytesIO(content)).read("word/document.xml").decode("utf-8")
    assert "ΑΙΣΤΟΟΥ ΥΠΗΡΕΣΙΕΣ ΙΝΤΕΡΝΕΤ Μ.ΙΚΕ" in xml
    assert "998031206" in xml
    assert "Μάκης Τουτουδάκης" in xml
    assert "erganiOS" in xml or "ΙΚΕ" in xml
    assert "__________" not in xml
    assert "___/___/____" not in xml
    assert agreement_filename(customer).endswith(".docx")


def test_offer_fills_customer_and_date():
    import zipfile
    from io import BytesIO

    customer = customer_for_agreement({
        "eponimia": "ΑΙΣΤΟΟΥ ΥΠΗΡΕΣΙΕΣ ΙΝΤΕΡΝΕΤ Μ.ΙΚΕ",
        "afm": "998031206",
        "address": "ΛΑΧΑΝΑ 17 ΠΕΡΙΣΤΕΡΙ ΤΚ 12131",
        "representative": "Μάκης Τουτουδάκης",
    })
    content = fill_offer_docx(customer)
    xml = zipfile.ZipFile(BytesIO(content)).read("word/document.xml").decode("utf-8")
    assert "ΑΙΣΤΟΟΥ ΥΠΗΡΕΣΙΕΣ ΙΝΤΕΡΝΕΤ Μ.ΙΚΕ" in xml
    assert "\u2026\u2026\u2026\u2026\u2026\u2026\u2026" not in xml
    assert "\u2026\u2026\u2026\u2026\u2026\u2026" not in xml
    assert offer_filename(customer).endswith(".docx")


def test_presentation_templates_and_email(monkeypatch):
    import pytest

    attachments = presentation_attachments()
    assert [name for name, _data in attachments] == [path.name for path in PRESENTATION_FILES]
    assert all(data.startswith(b"%PDF") for _name, data in attachments)
    items = presentation_items()
    assert [item["key"] for item in items] == ["apologistiko", "ai-agent"]
    assert presentation_file("apologistiko").name == "erganiOS_apologistiko_orometrisi.pdf"
    with pytest.raises(KeyError):
        presentation_file("missing")
    with pytest.raises(ValueError, match="Απαιτείται το email του πελάτη"):
        customer_for_presentation({"eponimia": "Δοκιμή ΑΕ"})
    with pytest.raises(ValueError, match="Μη έγκυρο email πελάτη"):
        customer_for_presentation({"email": "oxi-email"})
    recipient = customer_for_presentation({
        "eponimia": "Δοκιμή ΑΕ",
        "representative": "Μάκης Τουτουδάκης",
        "email": "client@example.gr",
    })
    monkeypatch.setattr("app.billing_presentation.Config.BILLING_CONTACT_PHONE", "6977392742")
    monkeypatch.setattr("app.billing_presentation.Config.BILLING_CONTACT_NAME", "Μάκης Τουτουδάκης")
    monkeypatch.setattr("app.billing_presentation.Config.BILLING_ISSUER_EMAIL", "info@erganios.gr")
    monkeypatch.setattr("app.billing_presentation.Config.PUBLIC_BASE_URL", "https://erganios.gr")
    text, html_body = build_presentation_email(recipient)
    assert PRESENTATION_SUBJECT
    assert PRESENTATION_BCC == "info@erganios.gr"
    assert "Παρακαλώ βρείτε επισυναπτόμενη μια συνοπτική παρουσίαση της υπηρεσίας erganiOS" in text
    assert "παραμένουμε στη διάθεσή σας για οποιαδήποτε διευκρίνιση." in text
    assert "Αξιότιμε/η κ. Μάκης Τουτουδάκης," in text
    assert "Με εκτίμηση,\nΜάκης Τουτουδάκης" in text
    assert "6977392742" in text
    assert "info@erganios.gr" in text
    assert "Web: https://erganios.gr" in text
    assert "Web: <a href=\"https://erganios.gr\"" in html_body
    assert "Παρακαλώ βρείτε επισυναπτόμενη" in html_body
    contact = presentation_contact()
    assert contact["name"] == "Μάκης Τουτουδάκης"
    assert contact["phone"] == "6977392742"
    assert contact["email"] == "info@erganios.gr"


def test_send_presentation_attaches_pdfs(monkeypatch):
    captured = {}

    def fake_send(to_email, subject, text_body, **kwargs):
        captured["to"] = to_email
        captured["subject"] = subject
        captured["text"] = text_body
        captured["kwargs"] = kwargs
        return {"ok": True, "to": to_email, "bcc": [PRESENTATION_BCC]}

    monkeypatch.setattr("app.billing_presentation.send_email_message", fake_send)
    result = send_presentation({
        "eponimia": "Δοκιμή ΑΕ",
        "email": "client@example.gr",
    })
    assert result["ok"] is True
    assert captured["to"] == "client@example.gr"
    assert captured["subject"] == PRESENTATION_SUBJECT
    assert captured["kwargs"]["bcc"] == PRESENTATION_BCC
    names = [name for name, _data in captured["kwargs"]["attachments"]]
    assert names == [path.name for path in PRESENTATION_FILES]


def test_agreement_requires_representative():
    import pytest

    with pytest.raises(ValueError, match="Απαιτείται το όνομα του εκπροσώπου"):
        customer_for_agreement({
            "eponimia": "ΑΙΣΤΟΟΥ ΥΠΗΡΕΣΙΕΣ ΙΝΤΕΡΝΕΤ Μ.ΙΚΕ",
            "afm": "998031206",
            "address": "ΛΑΧΑΝΑ 17",
        })


def test_invoice_form_placeholders():
    assert format_euro("1234.5") == "1.234,50"
    assert greek_date("2026-09-24") == "24/09/2026"
    issuer = issuer_profile()
    assert issuer["name"]
    assert issuer["afm"]
    assert len(issuer["banks"]) == 3
    assert all(item["iban"] for item in issuer["banks"])
    qr = qr_svg_data_uri("https://erganios.gr/ui/billing/invoice/1")
    assert qr.startswith("data:image/svg+xml;base64,")
    assert len(qr) > 80


def test_oxygen_tpy_payload_matches_room_schema(monkeypatch):
    monkeypatch.setattr("app.oxygen_invoice.Config.OXYGEN_ISSUER_VAT", "803072758")
    monkeypatch.setattr("app.oxygen_invoice.Config.OXYGEN_ISSUER_BRANCH", "0")
    payload = build_invoice_payload(
        customer={"eponimia": "Δοκιμή ΑΕ", "afm": "123456783", "address": "Οδός 1", "doy": "Αθήνα"},
        lines=[{
            "code": "SUB",
            "description": "ErganiOS + AI Agent 12 μήνες",
            "net": Decimal("100.00"),
            "vat": Decimal("24.00"),
            "gross": Decimal("124.00"),
            "vat_rate": Decimal("24.00"),
        }],
        doc_type="TPY",
        series="1",
        number=2001,
        total_net=Decimal("100.00"),
        total_vat=Decimal("24.00"),
        total_gross=Decimal("124.00"),
    )
    assert payload["header"]["invoice_type"] == "2.1"
    assert payload["counterpart"]["vat_number"] == "123456783"
    assert payload["lines"][0]["vat_category"] == 1
    assert payload["lines"][0]["classifications"][0]["type"] == "E3_561_001"
    assert classification_type("APY") == "E3_561_003"
    assert vat_category(Decimal("13.00")) == 2
    assert credit_invoice_type("TPY") == "5.1"
    assert credit_invoice_type("APY") == "11.4"
    credit = build_invoice_payload(
        customer={"eponimia": "Δοκιμή ΑΕ", "afm": "123456783", "address": "Οδός 1", "doy": "Αθήνα"},
        lines=[{
            "code": "CRD",
            "description": "Πιστωτικό",
            "net": Decimal("100.00"),
            "vat": Decimal("24.00"),
            "gross": Decimal("124.00"),
            "vat_rate": Decimal("24.00"),
        }],
        doc_type="CREDIT",
        series="Π",
        number=1,
        total_net=Decimal("100.00"),
        total_vat=Decimal("24.00"),
        total_gross=Decimal("124.00"),
        correlated_id="01m39rf2rg17r5az173dm6m391",
        source_doc_type="TPY",
    )
    assert credit["header"]["invoice_type"] == "5.1"
    assert credit["correlated_documents"] == ["01m39rf2rg17r5az173dm6m391"]
    assert credit["lines"][0]["classifications"][0]["type"] == "E3_561_001"
    assert permission_for_path("/api/billing/customers/3/stores", "PUT") == "billing.manage"
    assert permission_for_path("/api/store/list", "GET") == "stores.select"
