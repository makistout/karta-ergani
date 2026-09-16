"""Tests for WebMA (contract change) payload builder."""



from __future__ import annotations



import pytest



from app.web_ma_payload import (

    SUBMISSION_CODE_WEB_MA,

    build_web_ma_payload,

    draft_from_contract,

    map_regime,

    map_week_days,

    normalize_kyria_asfalish,

    normalize_epikourikiki_kod,

)

from app.work_card_payload import WorkCardPayloadError





_BRANCH_CODES = {

    "sepe_code": "11060",

    "oaed_code": "101202",

    "kad_code": "5611",

    "kallikratis_code": "91750201",

}



_IDENTITY = {

    "employee_afm": "123456789",

    "eponymo": "ΠΑΠΑΔΟΠΟΥΛΟΣ",

    "onoma": "ΓΙΩΡΓΟΣ",

    "onoma_patros": "ΝΙΚΟΣ",

    "onoma_mitros": "ΜΑΡΙΑ",

    "birthdate": "15/03/1990",

    "sex": "0",

    "yphkoothta": "025",

    "typos_taytothtas": "ΔAT",

    "ar_taytothtas": "ΑΒ123456",

    "amka": "15039012345",

}





def _base(**extra):

    return {

        **_IDENTITY,

        **_BRANCH_CODES,

        "change_types": ["002"],

        "basics_acceptance": "1",

        "specialty_code": "515",

        "specialty": "ΣΕΡΒΙΤΟΡΟΙ",

        "salary": "850",

        "weekly_hours": "40",

        **extra,

    }





def test_draft_prefills_from_contract():

    draft = draft_from_contract(

        {

            "employee_afm": "123456789",

            "eponymo": "ΠΑΠΑΔΟΠΟΥΛΟΣ",

            "onoma": "ΓΙΩΡΓΟΣ",

            "specialty": "Σερβιτόρος",

            "step92": "5123",

            "salary": "950,00",

            "weekly_hours": "40,0",

            "regime": "Πλήρης απασχόληση",

            "weekly_work_days": "5-ήμερο",

        },

        branch_aa="0",

        employee_afm="123456789",

    )

    assert draft["submission_code"] == SUBMISSION_CODE_WEB_MA

    assert draft["specialty_code"] == "5123"

    assert draft["change_types_catalog"]

    assert draft["basics_acceptance"] == "1"

    assert draft["yphkoothta"] == "025"





def test_build_web_ma_payload_hours_over_type():

    payload = build_web_ma_payload(

        _base(

            change_date="2026-09-16",

            change_types=["002", "013"],

            salary="1000",

            weekly_hours="28",

            weekly_work_days="5",

            regime="1",

            branch_aa="0",

        )

    )

    row = payload["AnaggeliesMA"]["AnaggeliaMA"][0]

    assert row["f_afm"] == "123456789"

    assert row["f_date_metabolhs"] == "16/09/2026"

    assert row["f_apodoxes"] == "1000,00"

    assert row["f_week_hours"] == "28,0"

    assert row["f_week_days"] == "5"

    assert row["f_kathestosapasxolisis"] == "1"

    assert row["f_onoma_patros"] == "ΝΙΚΟΣ"

    assert row["f_birthdate"] == "15/03/1990"

    assert row["f_kyria_asfalish"] == "001"

    assert row["Epikourikes"]["EpikourikesMA"][0]["f_epikouriki_kod"] == "001"

    codes = [x["f_typos_metabolhs"] for x in row["TypesMetabolon"]["TypesMetabolonMA"]]

    assert codes == ["002", "013"]





def test_normalize_kyria_asfalish():

    assert normalize_kyria_asfalish(None) == "001"

    assert normalize_kyria_asfalish("") == "001"

    assert normalize_kyria_asfalish("0") == "001"

    assert normalize_kyria_asfalish("1") == "001"

    assert normalize_kyria_asfalish("001") == "001"

    assert normalize_kyria_asfalish("002") == "002"

    assert normalize_kyria_asfalish("e-ΕΦΚΑ") == "001"

    assert normalize_kyria_asfalish("ΝΑΤ") == "002"

    assert (
        normalize_kyria_asfalish(
            "001-ΗΛΕΚΤΡΟΝΙΚΟΣ ΕΘΝΙΚΟΣ ΦΟΡΕΑΣ ΚΟΙΝΩΝΙΚΗΣ ΑΣΦΑΛΙΣΗΣ (e-ΕΦΚΑ)"
        )
        == "001"
    )

    assert normalize_epikourikiki_kod(None) == "001"

    assert normalize_epikourikiki_kod("0") == "001"

    assert (
        normalize_epikourikiki_kod("001-ΚΛΑΔΟΣ ΕΠΙΚΟΥΡΙΚΗΣ ΑΣΦΑΛΙΣΗΣ e-ΕΦΚΑ ")
        == "001"
    )

    assert normalize_epikourikiki_kod("ΤΕΚΑ") == "002"




def test_build_requires_change_type():


    with pytest.raises(WorkCardPayloadError):

        build_web_ma_payload(_base(change_types=[]))





def test_build_requires_pdf_when_file_acceptance():

    with pytest.raises(WorkCardPayloadError, match="PDF"):

        build_web_ma_payload(_base(basics_acceptance="0"))





def test_build_requires_branch_codes():

    data = _base()

    for key in _BRANCH_CODES:

        data.pop(key)

    with pytest.raises(WorkCardPayloadError, match="παραρτήματος"):

        build_web_ma_payload(data)





def test_build_requires_father_name():

    data = _base()

    data.pop("onoma_patros")

    with pytest.raises(WorkCardPayloadError, match="πατρός"):

        build_web_ma_payload(data)





def test_build_requires_amka():
    data = _base()
    data.pop("amka", None)
    data["amka"] = ""
    with pytest.raises(WorkCardPayloadError, match="ΑΜΚΑ"):
        build_web_ma_payload(data)


def test_build_includes_file_base64():

    payload = build_web_ma_payload(_base(basics_acceptance="0", f_file="JVBERi0x"))

    assert payload["AnaggeliesMA"]["AnaggeliaMA"][0]["f_file"] == "JVBERi0x"





def test_build_web_ma_xsd_required_field_order():

    payload = build_web_ma_payload(_base(change_types=["009"]))

    keys = list(payload["AnaggeliesMA"]["AnaggeliaMA"][0].keys())

    expected_prefix = [

        "f_aa_pararthmatos",

        "f_rel_protocol",

        "f_rel_date",

        "f_ypiresia_sepe",

        "f_ypiresia_oaed",

        "f_kad_pararthmatos",

        "f_kallikratis_pararthmatos",

        "f_eponymo",

        "f_onoma",

        "f_onoma_patros",

        "f_onoma_mitros",

        "f_birthdate",

        "f_sex",

        "f_yphkoothta",

        "f_typos_taytothtas",

        "f_ar_taytothtas",

        "f_ekdousa_arxh",

        "f_date_ekdosis",

        "f_date_ekdosis_lixi",

        "f_res_permit_inst",

        "f_res_permit_inst_type",

        "f_res_permit_inst_ar",

        "f_res_permit_inst_lixi",

        "f_res_permit_ap",

        "f_res_permit_ap_type",

        "f_res_permit_ap_ar",

        "f_res_permit_ap_lixi",

        "f_res_permit_visa",

        "f_res_permit_visa_ar",

        "f_res_permit_visa_from",

        "f_res_permit_visa_to",

        "f_marital_status",

        "f_arithmos_teknon",

        "f_afm",

        "f_doy",

        "f_amika",

        "f_amka",

        "f_code_anergias",

        "f_ar_vivliou_anilikou",

        "f_epipedo_morfosis",

    ]

    assert keys[: len(expected_prefix)] == expected_prefix

    assert keys.index("f_date_metabolhs") < keys.index("f_eidikothta")

    assert keys.index("f_eidikothta") < keys.index("f_apodoxes")

    assert keys.index("f_week_hours") < keys.index("f_basics_acceptance")

    assert keys.index("f_basics_acceptance") < keys.index("TypesMetabolon")

    assert keys.index("TypesMetabolon") < keys.index("Epikourikes")

    assert keys[-1] == "Epikourikes"





def test_map_helpers():
    assert map_regime("0") == "0"
    assert map_week_days("5") == "5"
