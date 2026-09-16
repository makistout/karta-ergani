"""Tests for WebE3N (hire / start of employment) payload builder."""

from __future__ import annotations

import pytest

from app.web_e3n_payload import (
    SUBMISSION_CODE_WEB_E3N,
    build_web_e3n_payload,
    empty_hire_draft,
)
from app.work_card_payload import WorkCardPayloadError


def test_empty_hire_draft_defaults():
    draft = empty_hire_draft(branch_aa="2")
    assert draft["submission_code"] == SUBMISSION_CODE_WEB_E3N
    assert draft["branch_aa"] == "2"
    assert draft["basics_acceptance"] == "1"
    assert draft["basics_acceptance_catalog"]


def test_build_web_e3n_payload_minimal():
    payload = build_web_e3n_payload(
        {
            "employee_afm": "123456789",
            "eponymo": "ΠΑΠΑΔΟΠΟΥΛΟΣ",
            "onoma": "ΓΙΩΡΓΟΣ",
            "onoma_patros": "ΝΙΚΟΣ",
            "onoma_mitros": "ΜΑΡΙΑ",
            "birthdate": "1990-05-15",
            "sex": "0",
            "typos_taytothtas": "ΑΤ",
            "ar_taytothtas": "ΑΒ123456",
            "hire_date": "2026-09-16",
            "hire_time_from": "09:00",
            "hire_time_to": "17:00",
            "specialty_code": "5123",
            "salary": "950",
            "weekly_hours": "40",
            "weekly_work_days": "5",
            "regime": "0",
            "employment_relation": "0",
            "basics_acceptance": "1",
            "branch_aa": "0",
        }
    )
    row = payload["AnaggeliesE3N"]["AnaggeliaE3N"][0]
    assert row["f_afm"] == "123456789"
    assert row["f_proslipsidate"] == "16/09/2026"
    assert row["f_birthdate"] == "15/05/1990"
    assert row["f_apodoxes"] == "950,00"
    assert row["f_week_hours"] == "40,0"
    assert row["f_eidikothta"] == "5123"
    assert row["f_basics_acceptance"] == "1"
    assert "f_file" not in row
    assert row["f_efarmoste_sillogiki_simbasi"] == "0"
    assert row["f_mh_provlepsimo_programma"] == "0"


def test_build_requires_names_and_parents():
    with pytest.raises(WorkCardPayloadError, match="πατρός"):
        build_web_e3n_payload(
            {
                "employee_afm": "123456789",
                "eponymo": "Α",
                "onoma": "Β",
                "birthdate": "1990-01-01",
                "sex": "0",
                "ar_taytothtas": "X1",
                "specialty_code": "1",
                "salary": "100",
                "weekly_hours": "40",
                "basics_acceptance": "1",
            }
        )


def test_build_requires_pdf_when_file_acceptance():
    with pytest.raises(WorkCardPayloadError, match="PDF"):
        build_web_e3n_payload(
            {
                "employee_afm": "123456789",
                "eponymo": "Α",
                "onoma": "Β",
                "onoma_patros": "Γ",
                "onoma_mitros": "Δ",
                "birthdate": "1990-01-01",
                "sex": "0",
                "ar_taytothtas": "X1",
                "specialty_code": "1",
                "salary": "100",
                "weekly_hours": "40",
                "basics_acceptance": "0",
            }
        )


def test_build_includes_file_base64():
    payload = build_web_e3n_payload(
        {
            "employee_afm": "123456789",
            "eponymo": "Α",
            "onoma": "Β",
            "onoma_patros": "Γ",
            "onoma_mitros": "Δ",
            "birthdate": "1990-01-01",
            "sex": "1",
            "ar_taytothtas": "X1",
            "specialty_code": "5123",
            "salary": "100",
            "weekly_hours": "40",
            "basics_acceptance": "0",
            "f_file": "JVBERi0x",
        }
    )
    assert payload["AnaggeliesE3N"]["AnaggeliaE3N"][0]["f_file"] == "JVBERi0x"
