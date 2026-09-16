"""Κατασκευή σώματος POST Documents/WebE3N — Ψηφιακή Αναγγελία Έναρξης Εργασίας (Πρόσληψη)."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from app.web_ma_payload import (
    _digits,
    _ergani_date,
    _hours,
    _money,
    map_characterization,
    map_employment_relation,
    map_regime,
    map_week_days,
    map_yes_no,
    specialty_code,
)
from app.work_card_payload import WorkCardPayloadError, norm_afm, tz_athens

SUBMISSION_CODE_WEB_E3N = "WebE3N"

BASICS_ACCEPTANCE_HIRE = [
    {"code": "0", "label": "Με επισυναπτόμενο αρχείο"},
    {"code": "1", "label": "Αναμονή αποδοχής εντός myErgani"},
]


def _hm(value: Any) -> str | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    m = re.fullmatch(r"(\d{1,2}):(\d{2})", raw)
    if not m:
        return None
    h, mi = int(m.group(1)), int(m.group(2))
    if h > 23 or mi > 59:
        return None
    return f"{h:02d}:{mi:02d}"


def empty_hire_draft(*, branch_aa: str = "0") -> dict[str, Any]:
    today = datetime.now(tz_athens()).strftime("%d/%m/%Y")
    return {
        "submission_code": SUBMISSION_CODE_WEB_E3N,
        "branch_aa": str(branch_aa or "0"),
        "employee_afm": "",
        "eponymo": "",
        "onoma": "",
        "onoma_patros": "",
        "onoma_mitros": "",
        "birthdate": "",
        "sex": "0",
        "amka": "",
        "amika": "",
        "typos_taytothtas": "ΔAT",
        "ar_taytothtas": "",
        "hire_date": today,
        "hire_time_from": "09:00",
        "hire_time_to": "17:00",
        "specialty": "",
        "specialty_code": "",
        "salary": "",
        "hourly_wage": "",
        "weekly_hours": "40,0",
        "fulltime_contract_weekly_hours": "40,0",
        "weekly_work_days": "5",
        "employment_relation": "0",
        "regime": "0",
        "characterization": "1",
        "fixed_term_from": "",
        "fixed_term_to": "",
        "prior_service": "0",
        "break_minutes": "30",
        "break_in_work": "1",
        "flex_arrival_minutes": "0",
        "working_time_digital_organization": "1",
        "working_card": "1",
        "trial_period": "0",
        "trial_date_to": "",
        "basics_acceptance": "1",
        "comments": "",
        "basics_acceptance_catalog": BASICS_ACCEPTANCE_HIRE,
    }


def build_web_e3n_payload(
    data: dict[str, Any],
    *,
    branch_aa: str | None = None,
) -> dict[str, Any]:
    afm = norm_afm(str(data.get("employee_afm") or data.get("f_afm") or ""))
    if not afm or len(afm) != 9:
        raise WorkCardPayloadError("Λείπει έγκυρο ΑΦΜ εργαζομένου")
    eponymo = str(data.get("eponymo") or data.get("f_eponymo") or "").strip()
    onoma = str(data.get("onoma") or data.get("f_onoma") or "").strip()
    father = str(data.get("onoma_patros") or data.get("f_onoma_patros") or "").strip()
    mother = str(data.get("onoma_mitros") or data.get("f_onoma_mitros") or "").strip()
    if not eponymo or not onoma:
        raise WorkCardPayloadError("Λείπουν επώνυμο / όνομα")
    if not father or not mother:
        raise WorkCardPayloadError("Λείπουν όνομα πατρός / μητρός")

    birth = str(data.get("birthdate") or data.get("f_birthdate") or "").strip()
    if not birth:
        raise WorkCardPayloadError("Λείπει ημερομηνία γέννησης")
    birth_ergani = _ergani_date(birth)

    sex = str(data.get("sex") or data.get("f_sex") or "").strip()
    if sex not in ("0", "1"):
        raise WorkCardPayloadError("Επιλέξτε φύλο")

    hire_date = _ergani_date(data.get("hire_date") or data.get("f_proslipsidate"))
    id_type = str(data.get("typos_taytothtas") or data.get("f_typos_taytothtas") or "ΔAT").strip()
    if id_type.upper() in ("ΑΤ", "AT", "ΔΑΤ", "DAT"):
        id_type = "ΔAT"
    id_no = str(data.get("ar_taytothtas") or data.get("f_ar_taytothtas") or "").strip()
    if not id_no:
        raise WorkCardPayloadError("Λείπει αριθμός ταυτότητας")

    acceptance = str(data.get("basics_acceptance") or data.get("f_basics_acceptance") or "1").strip()
    if acceptance not in ("0", "1"):
        raise WorkCardPayloadError("Μη έγκυρη αποδοχή ουσιωδών όρων")

    file_b64 = str(data.get("f_file") or data.get("file_base64") or "").strip()
    if file_b64.startswith("data:") and "," in file_b64:
        file_b64 = file_b64.split(",", 1)[1].strip()
    if acceptance == "0" and not file_b64:
        raise WorkCardPayloadError(
            "Για αποδοχή με επισυναπτόμενο αρχείο απαιτείται PDF ουσιωδών όρων"
        )
    if acceptance != "0":
        file_b64 = ""

    file_sym = str(data.get("f_file_symbash") or data.get("file_symbash_base64") or "").strip()
    if file_sym.startswith("data:") and "," in file_sym:
        file_sym = file_sym.split(",", 1)[1].strip()

    aa = str(
        data.get("branch_aa") or data.get("f_aa_pararthmatos") or branch_aa or "0"
    ).strip() or "0"

    relation = map_employment_relation(
        data.get("employment_relation") or data.get("f_sxeshapasxolisis")
    ) or "0"
    if relation == "3":
        relation = "0"  # WebE3N δεν έχει δανειζόμενο στο enum (0/1)
    regime = map_regime(data.get("regime") or data.get("f_kathestosapasxolisis")) or "0"
    week_days = map_week_days(data.get("weekly_work_days") or data.get("f_week_days")) or "5"
    week_hours = _hours(data.get("weekly_hours") or data.get("f_week_hours"))
    if not week_hours:
        raise WorkCardPayloadError("Λείπουν ώρες εβδομαδιαίως")
    salary = _money(data.get("salary") or data.get("f_apodoxes"))
    if not salary:
        raise WorkCardPayloadError("Λείπουν μεικτές αποδοχές")
    eid = specialty_code(
        data.get("specialty_code") or data.get("f_eidikothta"),
        data.get("step92"),
    )
    if not eid:
        raise WorkCardPayloadError("Λείπει κωδικός ειδικότητας")

    row: dict[str, Any] = {
        "f_aa_pararthmatos": aa,
        "f_eponymo": eponymo[:50],
        "f_onoma": onoma[:30],
        "f_onoma_patros": father[:30],
        "f_onoma_mitros": mother[:30],
        "f_birthdate": birth_ergani,
        "f_sex": sex,
        "f_typos_taytothtas": id_type[:10],
        "f_ar_taytothtas": id_no[:20],
        "f_afm": afm,
        "f_proslipsidate": hire_date,
        "f_week_hours": week_hours,
        "f_eidikothta": eid,
        "f_apodoxes": salary,
        "f_sxeshapasxolisis": relation,
        "f_kathestosapasxolisis": regime,
        "f_xaraktirismos": map_characterization(
            data.get("characterization") or data.get("f_xaraktirismos")
        )
        or "1",
        "f_week_days": week_days,
        "f_working_time_digital_organization": str(
            data.get("working_time_digital_organization") or "1"
        ),
        "f_working_card": str(data.get("working_card") or "1"),
        "f_basics_acceptance": acceptance,
        "f_trial_period": str(data.get("trial_period") or "0"),
        "f_marital_status": str(data.get("marital_status") or "0"),
        "f_topothetisioaed": "0",
        "f_mh_provlepsimo_programma": str(
            data.get("mh_provlepsimo_programma")
            or data.get("mh_problepsimo_programma")
            or "0"
        ),
    }

    optional: list[tuple[str, Any]] = [
        ("f_amka", _digits(data.get("amka") or data.get("f_amka"), max_len=20)),
        ("f_amika", _digits(data.get("amika") or data.get("f_amika"), max_len=20)),
        ("f_doy", _digits(data.get("doy") or data.get("f_doy"), max_len=4)),
        ("f_yphkoothta", _digits(data.get("yphkoothta") or data.get("f_yphkoothta"), max_len=3) or "025"),
        ("f_eidikothta_anal", str(data.get("specialty") or "").strip()[:255] or None),
        ("f_hour_apodoxes", _money(data.get("hourly_wage") or data.get("f_hour_apodoxes"))),
        (
            "f_full_employment_hours",
            _hours(
                data.get("fulltime_contract_weekly_hours")
                or data.get("f_full_employment_hours")
            )
            or "40,0",
        ),
        ("f_proipiresia", _digits(data.get("prior_service"), max_len=3) or "0"),
        ("f_proslipsitime", _hm(data.get("hire_time_from") or data.get("f_proslipsitime"))),
        ("f_apoxwrisitime", _hm(data.get("hire_time_to") or data.get("f_apoxwrisitime"))),
        ("f_dialeimma_minutes", _digits(data.get("break_minutes"), max_len=3)),
        ("f_dialeimma_entos_wrariou", map_yes_no(data.get("break_in_work")) or "1"),
        ("f_euelikto_wrario_minutes", _digits(data.get("flex_arrival_minutes"), max_len=3) or "0"),
        (
            "f_orismenou_apo",
            _ergani_date(data.get("fixed_term_from")) if data.get("fixed_term_from") else None,
        ),
        (
            "f_orismenou_ews",
            _ergani_date(data.get("fixed_term_to")) if data.get("fixed_term_to") else None,
        ),
        (
            "f_trial_date_to",
            _ergani_date(data.get("trial_date_to")) if data.get("trial_date_to") else None,
        ),
        ("f_file", file_b64 or None),
        ("f_file_symbash", file_sym or None),
        ("f_comments", str(data.get("comments") or "").strip()[:100] or None),
        ("f_arithmos_teknon", _digits(data.get("arithmos_teknon"), max_len=2) or "0"),
        ("f_epipedo_morfosis", _digits(data.get("epipedo_morfosis"), max_len=10) or "1"),
        ("f_topos_ergasias", str(data.get("topos_ergasias") or "0")),
        ("f_ipoxreotiki_katartisi", str(data.get("ipoxreotiki_katartisi") or "0")),
        (
            "f_efarmoste_sillogiki_simbasi",
            str(
                data.get("efarmoste_sillogiki_simbasi")
                or data.get("efarmostea_sillogiki_simbasi")
                or "0"
            ),
        ),
        ("f_responsible_position", str(data.get("responsible_position") or "1")),
        (
            "f_xronos_katavolis_apodoxon",
            str(data.get("xronos_katavolis_apodoxon") or "").strip()[:50] or None,
        ),
    ]
    for key, value in optional:
        if value is None or value == "":
            continue
        row[key] = value

    if relation == "1" and not row.get("f_orismenou_apo"):
        raise WorkCardPayloadError("Για ορισμένου χρόνου συμπληρώστε ημερομηνία από/έως")

    return {"AnaggeliesE3N": {"AnaggeliaE3N": [row]}}
