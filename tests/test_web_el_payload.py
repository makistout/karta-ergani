"""Tests for Ergani digital end-of-employment payloads."""

from __future__ import annotations

import pytest

from app.web_el_payload import (
    apply_contract_to_departure_draft,
    build_departure_payload,
    empty_departure_draft,
    event_date_iso,
)
from app.work_card_payload import WorkCardPayloadError


def _base(**extra):
    data = {
        "employee_afm": "143980812",
        "eponymo": "ΣΤΑΥΡΟΠΟΥΛΟΣ",
        "onoma": "ΓΕΩΡΓΙΟΣ",
        "onoma_patros": "ΝΙΚΟΣ",
        "onoma_mitros": "ΜΑΡΙΑ",
        "birthdate": "10/09/1984",
        "sex": "0",
        "typos_taytothtas": "ΔΑΤ",
        "ar_taytothtas": "ΑΒ123456",
        "hire_date": "12/07/2023",
        "event_date": "02/10/2026",
        "specialty_code": "413101",
        "salary": "534,17",
        "characterization": "0",
        "regime": "1",
        "employment_relation": "0",
        "branch_aa": "0",
        "f_file": "JVBERi0x",
    }
    data.update(extra)
    return data


def test_empty_draft_lists_ergani_types():
    draft = empty_departure_draft(branch_aa="2")
    codes = [row["code"] for row in draft["types"]]
    assert codes == ["WebE5N", "WebE6NXP", "WebE6NMP", "WebE7N", "WebE5O"]
    assert draft["branch_aa"] == "2"


def test_apply_contract_prefills_and_keeps_today_event():
    draft = empty_departure_draft()
    today = draft["event_date"]
    filled = apply_contract_to_departure_draft(
        draft,
        {
            "eponymo": "ΣΤΑΥΡΟΠΟΥΛΟΣ",
            "onoma": "ΓΕΩΡΓΙΟΣ",
            "characterization": "ΕΡΓΑΤΗΣ",
            "employment_relation": "ΑΟΡΙΣΤΟΥ ΧΡΟΝΟΥ",
            "salary": "534,17",
            "step92": "413101-ΑΠΟΘΗΚΑΡΙΟΙ",
            "hire_date": "2023-07-12",
        },
    )
    assert filled["eponymo"] == "ΣΤΑΥΡΟΠΟΥΛΟΣ"
    assert filled["characterization"] == "0"
    assert filled["specialty_code"] == "413101"
    assert filled["hire_date"] == "12/07/2023"
    assert filled["event_date"] == today


def test_apply_contract_fixed_term_defaults_event_to_contract_end():
    filled = apply_contract_to_departure_draft(
        empty_departure_draft(),
        {
            "employment_relation": "ΟΡΙΣΜΕΝΟΥ ΧΡΟΝΟΥ",
            "hire_date": "2023-07-12",
            "fixed_term_to": "2026-12-31",
            "salary": "499,92",
        },
    )
    assert filled["hire_date"] == "12/07/2023"
    assert filled["event_date"] == "31/12/2026"
    assert filled["submission_code"] == "WebE7N"


def test_webe5n_payload_and_event_iso():
    code, payload = build_departure_payload(_base(submission_code="WebE5N"))
    assert code == "WebE5N"
    row = payload["AnaggeliesE5N"]["AnaggeliaE5N"][0]
    assert row["f_afm"] == "143980812"
    assert row["f_apoxwrisidate"] == "02/10/2026"
    assert row["f_apodoxes"] == "534,17"
    assert row["f_file"] == "JVBERi0x"
    assert event_date_iso(_base(submission_code="WebE5N"), "WebE5N") == "2026-10-02"


def test_webe5n_requires_signed_pdf():
    with pytest.raises(WorkCardPayloadError, match="PDF"):
        build_departure_payload(_base(submission_code="WebE5N", f_file=""))


def test_webe6nxp_dismissal_fields():
    code, payload = build_departure_payload(
        _base(submission_code="WebE6NXP", compensation="1000,00", notice_date="01/10/2026")
    )
    row = payload["AnaggeliesE6NXP"]["AnaggeliaE6NXP"][0]
    assert code == "WebE6NXP"
    assert row["f_apolysisdate"] == "02/10/2026"
    assert row["f_koinopoihshdate"] == "01/10/2026"
    assert row["f_posoapozimiosis"] == "1000,00"
    assert row["f_omadiki"] == "0"


def test_webe6nmp_requires_notice_months():
    code, payload = build_departure_payload(
        _base(submission_code="WebE6NMP", notice_date="01/09/2026", notice_months="2")
    )
    row = payload["AnaggeliesE6NMP"]["AnaggeliaE6NMP"][0]
    assert code == "WebE6NMP"
    assert row["f_minesproidopoihsh"] == "2"
    assert row["f_proidopoihshdate"] == "01/09/2026"
    with pytest.raises(WorkCardPayloadError, match="μήνες"):
        build_departure_payload(
            _base(submission_code="WebE6NMP", notice_date="01/09/2026", notice_months="")
        )


def test_webe7n_fixed_term_without_file():
    code, payload = build_departure_payload(
        _base(
            submission_code="WebE7N",
            f_file="",
            employment_relation="1",
            fixed_term_to="30/09/2026",
            end_reason="0",
        )
    )
    row = payload["AnaggeliesE7N"]["AnaggeliaE7N"][0]
    assert code == "WebE7N"
    assert "f_file" not in row
    assert row["f_sxeshapasxolisis"] == "1"
    assert row["f_logosperatosis"] == "0"
    assert row["f_lixisymbashdate"] == "30/09/2026"


def test_detail_template_has_departure_button():
    from flask import Flask, render_template

    from app.access_control import register_access_context

    app = Flask(
        __name__,
        template_folder="app/templates",
        root_path=".",
    )
    app.secret_key = "test"
    register_access_context(app)

    with app.app_context():
        with app.test_request_context("/ui/employees/detail"):
            html = render_template("ui/employee-detail.html")
    assert "Αποχώρηση" in html
    assert "employeeDepartureModal" in html
    assert "Επιβεβαίωση αποχώρησης" in open(
        "app/static/js/employee-detail.js", encoding="utf-8"
    ).read()


def test_webe5o_does_not_update_employment():
    code, payload = build_departure_payload(_base(submission_code="WebE5O", f_file="", salary=""))
    assert code == "WebE5O"
    row = payload["AnaggeliesE5O"]["AnaggeliaE5O"][0]
    assert row["f_apoxwrisidate"] == "02/10/2026"
    assert event_date_iso(_base(submission_code="WebE5O"), "WebE5O") is None
