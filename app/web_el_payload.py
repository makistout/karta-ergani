"""Κατασκευή σώματος POST Documents/WebE5* / WebE6* / WebE7N — λήξη εργασίας."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app.web_ma_payload import (
    _digits,
    _ergani_date,
    _money,
    map_characterization,
    map_employment_relation,
    map_regime,
    specialty_code,
)
from app.work_card_payload import WorkCardPayloadError, norm_afm, tz_athens

DEPARTURE_TYPES: list[dict[str, Any]] = [
    {
        "code": "WebE5N",
        "label": "Οικειοθελής αποχώρηση",
        "group": "οικειοθελής",
        "needs_file": True,
        "file_hint": "Σαρωμένη δήλωση με υπογραφή εργαζομένου (ιδιόχειρη, gov.gr ή εγκεκριμένη ηλεκτρονική).",
        "event_date_label": "Ημερομηνία αποχώρησης",
        "updates_employment": True,
        "deadline_note": "Υποβολή εντός 4 εργάσιμων ημερών από το γεγονός.",
    },
    {
        "code": "WebE6NXP",
        "label": "Απόλυση χωρίς προειδοποίηση",
        "group": "απόλυση",
        "needs_file": True,
        "file_hint": "Σαρωμένη δήλωση με υπογραφές εργοδότη και εργαζομένου, ή εξώδικη + έκθεση επίδοσης.",
        "event_date_label": "Ημερομηνία απόλυσης",
        "updates_employment": True,
        "deadline_note": "Υποβολή εντός 4 εργάσιμων ημερών από το γεγονός.",
    },
    {
        "code": "WebE6NMP",
        "label": "Απόλυση με προειδοποίηση",
        "group": "απόλυση",
        "needs_file": True,
        "file_hint": "Σαρωμένη δήλωση με υπογραφές εργοδότη και εργαζομένου, ή εξώδικη + έκθεση επίδοσης.",
        "event_date_label": "Ημερομηνία λύσης (λήξη προειδοποίησης)",
        "updates_employment": True,
        "deadline_note": "Υποβολή εντός 4 εργάσιμων ημερών από το γεγονός.",
    },
    {
        "code": "WebE7N",
        "label": "Λύση σύμβασης ορισμένου χρόνου",
        "group": "ορισμένου",
        "needs_file": False,
        "file_hint": "",
        "event_date_label": "Ημερομηνία λήξης σύμβασης",
        "updates_employment": True,
        "deadline_note": "Υποβολή εντός 4 εργάσιμων ημερών από το γεγονός.",
    },
    {
        "code": "WebE5O",
        "label": "Όχληση για οικειοθελή αποχώρηση",
        "group": "οικειοθελής",
        "needs_file": False,
        "file_hint": "Μετά από αδικαιολόγητη απουσία άνω των 3 συνεχόμενων εργάσιμων ημερών.",
        "event_date_label": "Έναρξη αδικαιολόγητης απουσίας",
        "updates_employment": False,
        "deadline_note": "Μετά από 2 εργάσιμες χωρίς απόκριση υποβάλλεται οικειοθελής μετά από όχληση.",
    },
]

_TYPES_BY_CODE = {row["code"]: row for row in DEPARTURE_TYPES}

NOTICE_MONTHS = [
    {"code": "1", "label": "1 μήνας"},
    {"code": "2", "label": "2 μήνες"},
    {"code": "3", "label": "3 μήνες"},
    {"code": "4", "label": "4 μήνες"},
]

END_REASONS_E7 = [
    {"code": "0", "label": "Λήξη συμπεφωνημένου χρόνου"},
    {"code": "3", "label": "Καταγγελία Σ.Ο.Χ. με όρο πρόωρης καταγγελίας"},
    {"code": "4", "label": "Καταγγελία Σ.Ο.Χ. για σπουδαίο λόγο"},
    {"code": "5", "label": "Καταγγελία Σ.Ο.Χ. χωρίς σπουδαίο λόγο"},
    {"code": "6", "label": "Συναινετική λύση πριν τη λήξη"},
]

_WRAPPER = {
    "WebE5N": ("AnaggeliesE5N", "AnaggeliaE5N"),
    "WebE5O": ("AnaggeliesE5O", "AnaggeliaE5O"),
    "WebE6NXP": ("AnaggeliesE6NXP", "AnaggeliaE6NXP"),
    "WebE6NMP": ("AnaggeliesE6NMP", "AnaggeliaE6NMP"),
    "WebE7N": ("AnaggeliesE7N", "AnaggeliaE7N"),
}


def departure_type(code: str) -> dict[str, Any]:
    row = _TYPES_BY_CODE.get(str(code or "").strip())
    if not row:
        raise WorkCardPayloadError("Άγνωστος τύπος αποχώρησης")
    return row


def empty_departure_draft(*, branch_aa: str = "0") -> dict[str, Any]:
    today = datetime.now(tz_athens()).strftime("%d/%m/%Y")
    return {
        "submission_code": "WebE5N",
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
        "typos_taytothtas": "ΔΑΤ",
        "ar_taytothtas": "",
        "hire_date": "",
        "event_date": today,
        "notice_date": today,
        "specialty": "",
        "specialty_code": "",
        "salary": "",
        "compensation": "0,00",
        "characterization": "0",
        "employment_relation": "0",
        "regime": "0",
        "fixed_term_from": "",
        "fixed_term_to": "",
        "notice_months": "1",
        "collective": "0",
        "oros": "0",
        "end_reason": "0",
        "end_reason_comments": "",
        "comments": "",
        "types": DEPARTURE_TYPES,
        "notice_months_catalog": NOTICE_MONTHS,
        "end_reasons": END_REASONS_E7,
    }


def apply_contract_to_departure_draft(
    draft: dict[str, Any],
    found: dict[str, Any] | None,
) -> dict[str, Any]:
    out = dict(draft)
    row = found or {}
    mapped = {
        "characterization": map_characterization(row.get("characterization")),
        "employment_relation": _map_relation(row.get("employment_relation")),
        "regime": map_regime(row.get("regime")),
        "specialty_code": specialty_code(row.get("specialty_code"), row.get("step92")),
        "hire_date": _maybe_ergani_date(row.get("hire_date")),
        "birthdate": _maybe_ergani_date(row.get("birthdate")),
        "fixed_term_from": _maybe_ergani_date(row.get("fixed_term_from")),
        "fixed_term_to": _maybe_ergani_date(row.get("fixed_term_to") or row.get("departure_date")),
    }
    for key in (
        "eponymo",
        "onoma",
        "onoma_patros",
        "onoma_mitros",
        "sex",
        "amka",
        "amika",
        "typos_taytothtas",
        "ar_taytothtas",
        "specialty",
        "salary",
        "employee_afm",
        "sepe_code",
        "oaed_code",
        "kad_code",
        "kallikratis_code",
    ):
        value = row.get(key)
        if value is None or str(value).strip() == "":
            continue
        out[key] = value
    for key, value in mapped.items():
        if value:
            out[key] = value
    if row.get("employee_afm"):
        out["employee_afm"] = norm_afm(str(row.get("employee_afm")))
    if out.get("employment_relation") in ("1", "2"):
        out["submission_code"] = "WebE7N"
        if out.get("fixed_term_to"):
            out["event_date"] = out["fixed_term_to"]
    return out


def build_departure_payload(
    data: dict[str, Any],
    *,
    branch_aa: str | None = None,
) -> tuple[str, dict[str, Any]]:
    code = str(data.get("submission_code") or data.get("type") or "").strip()
    spec = departure_type(code)
    row = _identity_row(data, branch_aa=branch_aa)
    extras = _type_fields(code, data, spec)
    extras.update(_optional_files(data, spec))
    comments = str(data.get("comments") or data.get("f_comments") or "").strip()[:100]
    if comments:
        extras["f_comments"] = comments
    row.update(extras)
    wrapper, item = _WRAPPER[code]
    return code, {wrapper: {item: [row]}}


def event_date_iso(data: dict[str, Any], submission_code: str) -> str | None:
    spec = departure_type(submission_code)
    if not spec.get("updates_employment"):
        return None
    raw = data.get("event_date") or data.get("f_apoxwrisidate") or data.get("f_apolysisdate")
    text = _maybe_ergani_date(raw)
    if not text:
        return None
    day, month, year = text.split("/")
    return f"{year}-{month.zfill(2)}-{day.zfill(2)}"


def _map_relation(value: Any) -> str | None:
    text = str(value or "").strip().upper()
    if "ΕΡΓΟΥ" in text or text == "2":
        return "2"
    mapped = map_employment_relation(value)
    if mapped == "3":
        return "0"
    return mapped


def _maybe_ergani_date(value: Any) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    return _ergani_date(text)


def _require_date(value: Any, label: str) -> str:
    text = _maybe_ergani_date(value)
    if not text:
        raise WorkCardPayloadError(f"Λείπει {label}")
    return text


def _pdf_b64(data: dict[str, Any], key: str = "f_file") -> str:
    raw = str(data.get(key) or data.get("file_base64") or "").strip()
    if raw.startswith("data:") and "," in raw:
        raw = raw.split(",", 1)[1].strip()
    return raw


def _identity_row(data: dict[str, Any], *, branch_aa: str | None) -> dict[str, Any]:
    afm = norm_afm(str(data.get("employee_afm") or data.get("f_afm") or ""))
    if len(afm) != 9:
        raise WorkCardPayloadError("Λείπει έγκυρο ΑΦΜ εργαζομένου")
    eponymo = str(data.get("eponymo") or data.get("f_eponymo") or "").strip()
    onoma = str(data.get("onoma") or data.get("f_onoma") or "").strip()
    father = str(data.get("onoma_patros") or data.get("f_onoma_patros") or "").strip()
    mother = str(data.get("onoma_mitros") or data.get("f_onoma_mitros") or "").strip()
    if not eponymo or not onoma:
        raise WorkCardPayloadError("Λείπουν επώνυμο / όνομα")
    if not father or not mother:
        raise WorkCardPayloadError("Λείπουν όνομα πατρός / μητρός")
    birth = _require_date(data.get("birthdate") or data.get("f_birthdate"), "ημερομηνία γέννησης")
    sex = str(data.get("sex") or data.get("f_sex") or "").strip()
    if sex not in ("0", "1"):
        raise WorkCardPayloadError("Επιλέξτε φύλο")
    id_type = str(data.get("typos_taytothtas") or data.get("f_typos_taytothtas") or "ΔΑΤ").strip()
    if id_type.upper() in ("ΑΤ", "AT", "DAT", "ΔAT", "ΔΑT", "ΔAΤ"):
        id_type = "ΔΑΤ"
    id_no = str(data.get("ar_taytothtas") or data.get("f_ar_taytothtas") or "").strip()
    if not id_no:
        raise WorkCardPayloadError("Λείπει αριθμός ταυτότητας")
    aa = str(data.get("branch_aa") or data.get("f_aa_pararthmatos") or branch_aa or "0").strip() or "0"
    row: dict[str, Any] = {
        "f_aa_pararthmatos": aa,
        "f_eponymo": eponymo[:50],
        "f_onoma": onoma[:30],
        "f_onoma_patros": father[:30],
        "f_onoma_mitros": mother[:30],
        "f_birthdate": birth,
        "f_sex": sex,
        "f_typos_taytothtas": id_type[:10],
        "f_ar_taytothtas": id_no[:20],
        "f_afm": afm,
    }
    optional = [
        ("f_rel_protocol", str(data.get("f_rel_protocol") or data.get("rel_protocol") or "").strip() or None),
        ("f_rel_date", _maybe_ergani_date(data.get("f_rel_date") or data.get("rel_date"))),
        ("f_ypiresia_sepe", str(data.get("sepe_code") or data.get("f_ypiresia_sepe") or "").strip() or None),
        ("f_ypiresia_oaed", str(data.get("oaed_code") or data.get("f_ypiresia_oaed") or "").strip() or None),
        ("f_kad_pararthmatos", str(data.get("kad_code") or data.get("f_kad_pararthmatos") or "").strip() or None),
        (
            "f_kallikratis_pararthmatos",
            str(data.get("kallikratis_code") or data.get("f_kallikratis_pararthmatos") or "").strip() or None,
        ),
        ("f_yphkoothta", _digits(data.get("yphkoothta") or data.get("f_yphkoothta"), max_len=3) or "025"),
        ("f_amka", _digits(data.get("amka") or data.get("f_amka"), max_len=20)),
        ("f_amika", _digits(data.get("amika") or data.get("f_amika"), max_len=20)),
        ("f_marital_status", str(data.get("marital_status") or "0")),
        ("f_arithmos_teknon", _digits(data.get("arithmos_teknon"), max_len=2) or "0"),
        ("f_epipedo_morfosis", _digits(data.get("epipedo_morfosis"), max_len=10) or "1"),
    ]
    for key, value in optional:
        if value is None or value == "":
            continue
        row[key] = value
    return row


def _employment_core(data: dict[str, Any], *, relation: str | None = None) -> dict[str, Any]:
    eid = specialty_code(
        data.get("specialty_code") or data.get("f_eidikothta"),
        data.get("step92") or data.get("specialty"),
    )
    if not eid:
        raise WorkCardPayloadError("Λείπει κωδικός ειδικότητας")
    hire = _require_date(data.get("hire_date") or data.get("f_proslipsidate"), "ημερομηνία πρόσληψης")
    out = {
        "f_xaraktirismos": map_characterization(
            data.get("characterization") or data.get("f_xaraktirismos")
        )
        or "0",
        "f_kathestosapasxolisis": map_regime(data.get("regime") or data.get("f_kathestosapasxolisis"))
        or "0",
        "f_eidikothta": eid,
        "f_proslipsidate": hire,
    }
    if relation is not None:
        out["f_sxeshapasxolisis"] = relation
        if relation in ("1", "2"):
            fixed_from = _maybe_ergani_date(data.get("fixed_term_from") or data.get("f_orismenou_apo"))
            fixed_to = _maybe_ergani_date(data.get("fixed_term_to") or data.get("f_orismenou_ews"))
            if fixed_from:
                out["f_orismenou_apo"] = fixed_from
            if fixed_to:
                out["f_orismenou_ews"] = fixed_to
    return out


def _require_salary(data: dict[str, Any]) -> str:
    salary = _money(data.get("salary") or data.get("f_apodoxes"))
    if not salary:
        raise WorkCardPayloadError("Λείπουν μεικτές αποδοχές κατά την αποχώρηση")
    return salary


def _optional_files(data: dict[str, Any], spec: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    file_b64 = _pdf_b64(data)
    if spec.get("needs_file") and not file_b64:
        raise WorkCardPayloadError("Απαιτείται PDF υπογεγραμμένης δήλωσης")
    if file_b64:
        out["f_file"] = file_b64
    return out


def _type_fields(code: str, data: dict[str, Any], spec: dict[str, Any]) -> dict[str, Any]:
    event = _require_date(
        data.get("event_date") or data.get("f_apoxwrisidate") or data.get("f_apolysisdate"),
        spec["event_date_label"].lower(),
    )
    if code == "WebE5N":
        relation = _map_relation(data.get("employment_relation") or data.get("f_sxeshapasxolisis")) or "0"
        if relation not in ("0", "1", "2"):
            relation = "0"
        out = _employment_core(data, relation=relation)
        out["f_apoxwrisidate"] = event
        out["f_apodoxes"] = _require_salary(data)
        return out
    if code == "WebE5O":
        relation = _map_relation(data.get("employment_relation") or data.get("f_sxeshapasxolisis")) or "0"
        if relation not in ("0", "1"):
            relation = "0"
        out = _employment_core(data, relation=relation)
        out["f_apoxwrisidate"] = event
        return out
    if code == "WebE6NXP":
        out = _employment_core(data)
        out["f_omadiki"] = "1" if str(data.get("collective") or "0").strip() == "1" else "0"
        if out["f_omadiki"] == "1":
            decision = str(data.get("collective_no") or data.get("f_omadikiarithmos") or "").strip()
            if decision:
                out["f_omadikiarithmos"] = decision[:20]
            decision_date = _maybe_ergani_date(data.get("collective_date") or data.get("f_omadikidate"))
            if decision_date:
                out["f_omadikidate"] = decision_date
        out["f_apolysisdate"] = event
        out["f_apodoxes"] = _require_salary(data)
        notice = _maybe_ergani_date(data.get("notice_date") or data.get("f_koinopoihshdate")) or event
        out["f_koinopoihshdate"] = notice
        compensation = _money(data.get("compensation") or data.get("f_posoapozimiosis")) or "0,00"
        out["f_posoapozimiosis"] = compensation
        return out
    if code == "WebE6NMP":
        out = _employment_core(data)
        notice = _require_date(
            data.get("notice_date") or data.get("f_proidopoihshdate"),
            "ημερομηνία προειδοποίησης",
        )
        months = str(data.get("notice_months") or data.get("f_minesproidopoihsh") or "").strip()
        if months not in ("1", "2", "3", "4"):
            raise WorkCardPayloadError("Επιλέξτε μήνες προειδοποίησης (1–4)")
        out["f_proidopoihshdate"] = notice
        out["f_minesproidopoihsh"] = months
        out["f_omadiki"] = "1" if str(data.get("collective") or "0").strip() == "1" else "0"
        out["f_apolysisdate"] = event
        out["f_apodoxes"] = _require_salary(data)
        out["f_posoapozimiosis"] = _money(data.get("compensation") or data.get("f_posoapozimiosis")) or "0,00"
        return out
    if code == "WebE7N":
        relation = _map_relation(data.get("employment_relation") or data.get("f_sxeshapasxolisis")) or "1"
        if relation not in ("1", "2"):
            relation = "1"
        out = _employment_core(data, relation=relation)
        out["f_oros"] = "1" if str(data.get("oros") or "0").strip() == "1" else "0"
        out["f_apodoxes"] = _require_salary(data)
        contract_end = _maybe_ergani_date(
            data.get("fixed_term_to") or data.get("f_lixisymbashdate")
        ) or event
        out["f_lixisymbashdate"] = contract_end
        out["f_apolysisdate"] = event
        reason = str(data.get("end_reason") or data.get("f_logosperatosis") or "0").strip()
        if reason not in ("0", "3", "4", "5", "6"):
            raise WorkCardPayloadError("Επιλέξτε λόγο περάτωσης ορισμένου χρόνου")
        out["f_logosperatosis"] = reason
        reason_notes = str(data.get("end_reason_comments") or data.get("f_logosperatosiscomments") or "").strip()
        if reason_notes:
            out["f_logosperatosiscomments"] = reason_notes[:100]
        return out
    raise WorkCardPayloadError("Άγνωστος τύπος αποχώρησης")
