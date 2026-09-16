"""Κατασκευή σώματος POST Documents/WebMA — μεταβολή στοιχείων εργασιακής σχέσης."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from app.work_card_payload import WorkCardPayloadError, norm_afm, tz_athens

SUBMISSION_CODE_WEB_MA = "WebMA"
SUBMISSION_CODE_WEB_MAD = "WebMAD"

# Κωδικοί τύπου μεταβολής — Οδηγός ΕΡΓΑΝΗ ΙΙ (έκδ. 13.02.2026)
CHANGE_TYPES: list[dict[str, str]] = [
    {"code": "001", "label": "Μεταβολή αποδοχών λόγω αλλαγής νομοθεσίας"},
    {"code": "002", "label": "Μεταβολή αποδοχών κατόπιν συμφωνίας"},
    {"code": "003", "label": "Κτήση ιδιότητας διευθυντικού στελέχους"},
    {"code": "004", "label": "Απώλεια ιδιότητας διευθυντικού στελέχους"},
    {"code": "005", "label": "Παράταση ισχύος σύμβασης ορισμένου χρόνου"},
    {"code": "006", "label": "Μετατροπή σύμβασης ορισμένου χρόνου σε αορίστου χρόνου"},
    {"code": "007", "label": "Μετατροπή μερικής (ή εκ περιτροπής) απασχόλησης σε πλήρη"},
    {"code": "008", "label": "Μετατροπή πλήρους απασχόλησης σε μερική"},
    {"code": "009", "label": "Μεταβολή ειδικότητας"},
    {"code": "010", "label": "Μεταβολή τόπου παροχής εργασίας"},
    {"code": "011", "label": "Ένταξη στην ψηφιακή κάρτα"},
    {"code": "012", "label": "Δανεισμός"},
    {"code": "013", "label": "Αλλαγές Ψηφιακής Οργάνωσης Χρόνου Εργασίας"},
    {"code": "014", "label": "Μετατροπή πλήρους σε εκ περιτροπής"},
    {"code": "015", "label": "Μετατροπή πλήρους σε εκ περιτροπής (μονομερώς)"},
    {"code": "016", "label": "Διευθέτηση του χρόνου εργασίας"},
    {"code": "999", "label": "Άλλο / άλλη περίπτωση"},
]

_CHANGE_CODES = {row["code"] for row in CHANGE_TYPES}

BASICS_ACCEPTANCE = [
    {"code": "0", "label": "Με επισυναπτόμενο αρχείο"},
    {"code": "1", "label": "Αναμονή αποδοχής εντός myErgani"},
    {"code": "2", "label": "Δεν απαιτείται"},
]

# EX_BASE_03 / TyposTaytotitas — κωδικοί Ergani (όχι πλήρη λεκτικά).
IDENTITY_DOCUMENT_TYPES: list[dict[str, str]] = [
    {"code": "ΔΑΤ", "label": "ΔΕΛΤΙΟ ΑΣΤΥΝΟΜΙΚΗΣ ΤΑΥΤΟΤΗΤΑΣ"},
    {"code": "ΔΙΑ", "label": "ΔΙΑΒΑΤΗΡΙΟ"},
    {"code": "ΑΔΑ", "label": "ΑΔΕΙΑ ΔΙΑΜΟΝΗΣ (ΒΙΝΙΕΤΑ)"},
    {"code": "ΑΔΠΑΕ", "label": "ΑΔΕΙΑ ΔΙΑΜΟΝΗΣ ΜΕ ΔΙΚΑΙΩΜΑ ΕΡΓΑΣΙΑΣ"},
    {"code": "ΒΕΕ", "label": "ΒΕΒΑΙΩΣΗ ΕΓΓΡΑΦΗΣ ΠΟΛΙΤΩΝ Ε.Ε."},
    {"code": "ΒΚΑΕΑΔ", "label": "ΒΕΒΑΙΩΣΗ ΚΑΤΑΘΕΣΗΣ ΑΙΤΗΣΗΣ ΓΙΑ ΑΔΕΙΑ ΔΙΑΜΟΝΗΣ"},
    {"code": "ΔΑΑ", "label": "ΔΕΛΤΙΟ ΑΙΤΟΥΝΤΟΣ ΑΣΥΛΟ"},
    {"code": "ΔΔΤΧ", "label": "ΔΕΛΤΙΟ ΔΙΑΜΟΝΗΣ ΠΟΛΙΤΩΝ ΤΡΙΤΩΝ ΧΩΡΩΝ"},
    {"code": "ΔΕΕ", "label": "ΔΕΛΤΙΟ ΜΟΝΙΜΗΣ ΔΙΑΜΟΝΗΣ ΠΟΛΙΤΩΝ Ε.Ε."},
    {"code": "ΕΒΝΔ", "label": "ΕΙΔΙΚΗ ΒΕΒΑΙΩΣΗ ΝΟΜΙΜΗΣ ΔΙΑΜΟΝΗΣ"},
    {"code": "ΕΔΤΟ", "label": "ΕΙΔΙΚΟ ΔΕΛΤΙΟ ΤΑΥΤΟΤΗΤΑΣ ΟΜΟΓΕΝΟΥΣ"},
    {"code": "ΤΧΕΕ", "label": "ΤΑΥΤΟΤΗΤΑ ΧΩΡΩΝ ΕΥΡΩΠΑΪΚΗΣ ΕΝΩΣΗΣ"},
]
_IDENTITY_CODES = {row["code"] for row in IDENTITY_DOCUMENT_TYPES}
DEFAULT_IDENTITY_TYPE = "ΔΑΤ"

# EX_BASE_03 / ForeisKyriasAsfalisis — κωδικοί κύριας ασφάλισης (όχι "0").
MAIN_INSURANCE_FUNDS: list[dict[str, str]] = [
    {
        "code": "001",
        "label": "ΗΛΕΚΤΡΟΝΙΚΟΣ ΕΘΝΙΚΟΣ ΦΟΡΕΑΣ ΚΟΙΝΩΝΙΚΗΣ ΑΣΦΑΛΙΣΗΣ (e-ΕΦΚΑ)",
    },
    {
        "code": "002",
        "label": "e-ΕΦΚΑ – ΝΑΥΤΙΚΟ ΑΠΟΜΑΧΙΚΟ ΤΑΜΕΙΟ (ΝΑΤ)",
    },
    {
        "code": "003",
        "label": "ΤΡΑΠΕΖΑ ΤΗΣ ΕΛΛΑΔΟΣ – πρ. ΤΑΜΕΙΟ ΣΥΝΤΑΞΕΩΝ ΤΟΥ ΠΡΟΣΩΠΙΚΟΥ ΤΗΣ ΤΡΑΠΕΖΑΣ ΤΗΣ ΕΛΛΑΔΟΣ",
    },
]
_MAIN_INSURANCE_CODES = {row["code"] for row in MAIN_INSURANCE_FUNDS}
DEFAULT_KYRIA_ASFALISH = "001"

# EX_BASE_03 / είδος διευθέτησης χρόνου εργασίας (WebMA).
DIEUTHETISI_TYPES: list[dict[str, str]] = [
    {"code": "2", "label": "Όχι"},
    {"code": "0", "label": "Ναι — συλλογική συμφωνία"},
    {"code": "1", "label": "Ναι — ατομική συμφωνία"},
]
DEFAULT_DIEUTHETISI = "2"

# EX_BASE_03 / ForeisEpikourikisAsfalisis
SUPPLEMENTARY_INSURANCE_FUNDS: list[dict[str, str]] = [
    {"code": "001", "label": "ΚΛΑΔΟΣ ΕΠΙΚΟΥΡΙΚΗΣ ΑΣΦΑΛΙΣΗΣ e-ΕΦΚΑ"},
    {"code": "002", "label": "ΤΑΜΕΙΟ ΕΠΙΚΟΥΡΙΚΗΣ ΚΕΦΑΛΑΙΟΠΟΙΗΤΙΚΗΣ ΑΣΦΑΛΙΣΗΣ (ΤΕΚΑ)"},
    {
        "code": "003",
        "label": "ΕΠΑΓΓΕΛΜΑΤΙΚΟ ΤΑΜΕΙΟ ΕΠΙΚΟΥΡΙΚΗΣ ΑΣΦΑΛΙΣΗΣ ΠΡΟΣΩΠΙΚΟΥ ΕΤΑΙΡΕΙΩΝ ΠΕΤΡΕΛΑΙΟΕΙΔΩΝ (ΕΤΕΑΠΕΠ)",
    },
    {
        "code": "004",
        "label": "ΤΑΜΕΙΟ ΕΠΑΓΓΕΛΜΑΤΙΚΗΣ ΑΣΦΑΛΙΣΗΣ ΥΠΑΛΛΗΛΩΝ ΦΑΡΜΑΚΕΥΤΙΚΩΝ ΕΡΓΑΣΙΩΝ (ΤΕΑΥΦΕ)",
    },
    {
        "code": "005",
        "label": "ΤΑΜΕΙΟ ΕΠΑΓΓΕΛΜΑΤΙΚΗΣ ΑΣΦΑΛΙΣΗΣ ΥΠΑΛΛΗΛΩΝ ΕΜΠΟΡΙΟΥ ΤΡΟΦΙΜΩΝ (ΤΕΑΥΕΤ)",
    },
    {
        "code": "006",
        "label": "ΤΑΜΕΙΟ ΕΠΑΓΓΕΛΜΑΤΙΚΗΣ ΑΣΦΑΛΙΣΗΣ ΕΠΙΚΟΥΡΗΣΗΣ ΑΣΦΑΛΙΣΤΩΝ ΚΑΙ ΠΡΟΣΩΠΙΚΟΥ ΑΣΦΑΛΙΣΤΙΚΩΝ ΕΠΙΧΕΙΡΗΣΕΩΝ (ΤΕΑ-ΕΑΠΑΕ)",
    },
    {
        "code": "007",
        "label": "ΕΝΙΑΙΟΣ ΔΗΜΟΣΙΟΓΡΑΦΙΚΟΣ ΟΡΓΑΝΙΣΜΟΣ ΕΠΙΚΟΥΡΙΚΗΣ ΑΣΦΑΛΙΣΗΣ ΠΕΡΙΘΑΛΨΗΣ (ΕΔΟΕΑΠ)",
    },
    {"code": "008", "label": "ΜΕΤΟΧΙΚΟ ΤΑΜΕΙΟ ΠΟΛΙΤΙΚΩΝ ΥΠΑΛΛΗΛΩΝ (ΜΤΠΥ)"},
    {
        "code": "009",
        "label": "ΤΡΑΠΕΖΑ ΤΗΣ ΕΛΛΑΔΟΣ – πρ. ΜΕΤΟΧΙΚΟ ΤΑΜΕΙΟ ΠΟΛΙΤΙΚΩΝ ΥΠΑΛΛΗΛΩΝ",
    },
    {"code": "010", "label": "ΚΛΑΔΟΣ ΕΠΙΚΟΥΡΙΚΗΣ ΑΣΦΑΛΙΣΗΣ ΝΑΥΤΙΚΩΝ (ΚΕΑΝ)"},
]
_SUPPLEMENTARY_INSURANCE_CODES = {row["code"] for row in SUPPLEMENTARY_INSURANCE_FUNDS}
DEFAULT_EPIKOURIKIKI = "001"

# Σειρά στοιχείων AnaggeliaMA από XSD/Lookup Ergani (Documents/WebMA).
# Η σειρά μετράει — διαφορετικά το Ergani επιστρέφει invalid child element.
_ANAGGELIA_MA_FIELD_ORDER: tuple[str, ...] = (
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
    "f_date_metabolhs",
    "f_eidos_dieuthethshs",
    "f_eidos_dieuthethshs_comments",
    "f_periodos_anaforas_from",
    "f_periodos_anaforas_to",
    "f_eidikothta",
    "f_eidikothta_anal",
    "f_proipiresia",
    "f_apodoxes",
    "f_hour_apodoxes",
    "f_xronos_katabolhs",
    "f_topos_ergasias",
    "f_topos_ergasias_comments",
    "f_sxeshapasxolisis",
    "f_orismenou_apo",
    "f_orismenou_ews",
    "f_kathestosapasxolisis",
    "f_xaraktirismos",
    "f_special_case",
    "f_responsible_position",
    "f_efarmostea_sillogiki_simbasi",
    "f_efarmostea_sillogiki_simbasi_comments",
    "f_kyria_asfalish",
    "f_prosthetes_asfalistikes_paroxes",
    "f_ipoxreotiki_katartisi",
    "f_working_time_digital_organization",
    "f_mh_problepsimo_programma",
    "f_paraggelia_hmeres_hours",
    "f_paraggelia_min_notification",
    "f_paraggelia_notes",
    "f_week_hours",
    "f_full_employment_hours",
    "f_week_days",
    "f_euelikto_wrario_minutes",
    "f_working_card",
    "f_dialeimma_minutes",
    "f_dialeimma_entos_wrariou",
    "f_topothetisioaed",
    "f_programaoaed",
    "f_trial_period",
    "f_trial_date_to",
    "f_borrow_type",
    "f_borrow_date_from",
    "f_borrow_date_to",
    "f_borrow_company_afm",
    "f_borrow_company_eponimia",
    "f_basics_acceptance",
    "f_file",
    "f_comments",
    "f_foreign_file",
    "f_young_file",
    "f_epibolh_file",
    "TypesMetabolon",
    "Epikourikes",
)

# Πεδία που το XSD sequence απαιτεί πριν τα επόμενα, ακόμα κι αν είναι «κενά».
_XSD_SEQUENCE_DEFAULTS: dict[str, str] = {
    "f_eidos_dieuthethshs": "2",
    "f_eidos_dieuthethshs_comments": "",
    "f_periodos_anaforas_from": " ",
    "f_periodos_anaforas_to": " ",
    "f_eidikothta_anal": "",
    "f_xronos_katabolhs": "Μηνιαίως",
    "f_topos_ergasias_comments": "",
    "f_orismenou_apo": " ",
    "f_orismenou_ews": " ",
    "f_special_case": "",
    "f_responsible_position": "",
    "f_efarmostea_sillogiki_simbasi_comments": "",
    "f_kyria_asfalish": DEFAULT_KYRIA_ASFALISH,
    "f_prosthetes_asfalistikes_paroxes": "",
    "f_paraggelia_hmeres_hours": "",
    "f_paraggelia_min_notification": "",
    "f_paraggelia_notes": "",
    "f_programaoaed": "",
    "f_trial_date_to": " ",
    # "" = χωρίς δανεισμό. Το «0» σημαίνει ΔΑΝΕΙΖΩΝ και απαιτεί ΑΦΜ/επωνυμία/ημ/νίες.
    "f_borrow_type": "",
    "f_borrow_date_from": " ",
    "f_borrow_date_to": " ",
    "f_borrow_company_afm": "",
    "f_borrow_company_eponimia": "",
    "f_comments": "",
    "f_file": "AA==",
    # Κενό (όχι AA==): το Ergani θεωρεί το AA== επισυναπτόμενο αρχείο.
    "f_foreign_file": "",
    "f_young_file": "",
    "f_epibolh_file": "",
}


def _ordered_anaggelia_ma(values: dict[str, Any]) -> dict[str, Any]:
    """Κρατά πεδία στη σειρά του XSD (παραλείπει μόνο None)."""
    out: dict[str, Any] = {}
    for key in _ANAGGELIA_MA_FIELD_ORDER:
        if key not in values:
            continue
        value = values[key]
        if value is None:
            continue
        out[key] = value
    return out


def _res_permit_flag(value: Any) -> str:
    raw = str(value or "").strip()
    if raw in ("0", "1"):
        return raw
    if raw in ("", "None", "null"):
        return "0"
    return "0"


def _optional_text(value: Any, *, max_len: int | None = None) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    if max_len is not None:
        return text[:max_len]
    return text


def _ergani_date(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return datetime.now(tz_athens()).strftime("%d/%m/%Y")
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text[:10]):
        y, m, d = text[:10].split("-")
        return f"{int(d):02d}/{int(m):02d}/{y}"
    if "/" in text:
        return text[:10]
    return datetime.now(tz_athens()).strftime("%d/%m/%Y")


def _money(value: Any) -> str | None:
    raw = str(value or "").strip().replace("€", "").replace(" ", "")
    if not raw:
        return None
    if "," in raw and "." in raw:
        raw = raw.replace(".", "").replace(",", ".")
    elif "," in raw:
        raw = raw.replace(",", ".")
    try:
        amount = float(raw)
    except ValueError:
        return None
    whole, frac = f"{amount:.2f}".split(".")
    return f"{whole},{frac}"


def _hours(value: Any) -> str | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    raw = raw.replace(",", ".")
    try:
        num = float(raw)
    except ValueError:
        m = re.search(r"\d+(?:[.,]\d+)?", raw)
        if not m:
            return None
        num = float(m.group(0).replace(",", "."))
    whole, frac = f"{num:.1f}".split(".")
    return f"{int(float(whole))},{frac}"


def _digits(value: Any, *, max_len: int | None = None) -> str | None:
    digits = re.sub(r"\D", "", str(value or ""))
    if not digits:
        return None
    if max_len is not None:
        digits = digits[:max_len]
    return digits


def map_employment_relation(value: Any) -> str | None:
    text = str(value or "").strip().upper()
    if not text:
        return None
    if "ΔΑΝΕΙ" in text:
        return "3"
    if "ΟΡΙΣΜΕΝ" in text:
        return "1"
    if "ΑΟΡΙΣΤ" in text:
        return "0"
    return _enum_digit_code(value, allowed={"0", "1", "3"})


def map_regime(value: Any) -> str | None:
    text = str(value or "").strip().upper()
    if not text:
        return None
    if "ΠΛΗΡ" in text:
        return "0"
    if "ΜΕΡΙΚ" in text:
        return "1"
    if "ΠΕΡΙΤΡΟΠ" in text or "ΕΚ ΠΕΡ" in text:
        return "2"
    return _enum_digit_code(value, allowed={"0", "1", "2"})


def map_week_days(value: Any) -> str | None:
    text = str(value or "").strip()
    if "6" in text:
        return "6"
    if "5" in text:
        return "5"
    if text in ("5", "6"):
        return text
    return None


def map_yes_no(value: Any) -> str | None:
    if value is None or value == "":
        return None
    if value in (1, True, "1", "ΝΑΙ", "Ναι", "yes", "YES"):
        return "1"
    if value in (0, False, "0", "ΟΧΙ", "Όχι", "no", "NO"):
        return "0"
    return None


def normalize_topos_ergasias(value: Any, *, default: str = "0") -> str:
    """XSD enum τόπου εργασίας — μόνο ψηφίο (π.χ. 0), όχι λεκτικό EX_BASE_05."""
    text = str(value or "").strip()
    if not text:
        return default
    if text in ("0", "1", "2", "3"):
        return text
    # π.χ. «ΠΑΡΑΡΤΗΜΑ ΕΡΓΟΔΟΤΗ (0)»
    m = re.search(r"\((\d)\)\s*$", text)
    if m:
        return m.group(1)
    digit = _enum_digit_code(text, allowed={"0", "1", "2", "3"})
    if digit is not None:
        return digit
    upper = text.upper()
    if "ΠΑΡΑΡΤΗΜ" in upper or "ΕΡΓΟΔΟΤ" in upper:
        return "0"
    return default


def normalize_yes_no_flag(value: Any, *, default: str = "0") -> str:
    """Ναι/Όχι ή «0-Όχι» / «1-Ναι» από EX_BASE_05 → 0/1."""
    mapped = map_yes_no(value)
    if mapped is not None:
        return mapped
    text = str(value or "").strip()
    if not text:
        return default
    m = re.match(r"^([01])\b", text)
    if m:
        return m.group(1)
    m = re.search(r"\(([01])\)\s*$", text)
    if m:
        return m.group(1)
    return _enum_digit_code(text, allowed={"0", "1"}, default=default) or default


def map_characterization(value: Any) -> str | None:
    text = str(value or "").strip().upper()
    if "ΕΡΓΑΤ" in text:
        return "0"
    if "ΥΠΑΛΛ" in text:
        return "1"
    code = _enum_digit_code(value, allowed={"0", "1"})
    if code:
        return code
    return None


def _enum_digit_code(
    value: Any,
    *,
    allowed: set[str] | None = None,
    default: str | None = None,
) -> str | None:
    """Κανονικοποιεί τιμές τύπου 'ΑΓΑΜΟΣ/Η (0)' → '0'."""
    raw = str(value or "").strip()
    if not raw:
        return default
    if allowed is not None and raw in allowed:
        return raw
    if allowed is None and re.fullmatch(r"\d+", raw):
        return raw
    m = re.search(r"\((\d+)\)\s*$", raw)
    if m:
        code = m.group(1)
        if allowed is None or code in allowed:
            return code
    m = re.match(r"^(\d+)", raw)
    if m:
        code = m.group(1)
        if allowed is None or code in allowed:
            return code
    return default


def specialty_code(value: Any, step92: Any = None) -> str | None:
    for candidate in (step92, value):
        digits = _digits(candidate, max_len=6)
        if digits:
            return digits
    return None


def normalize_kyria_asfalish(value: Any, *, default: str = DEFAULT_KYRIA_ASFALISH) -> str:
    """Κωδικός ForeisKyriasAsfalisis (001/002/003). Το «0» δεν είναι έγκυρο."""
    text = str(value or "").strip().upper()
    if not text:
        return default
    m = re.match(r"^(\d{1,6})", text)
    if m and m.group(1) != "0":
        raw = m.group(1)
        padded = raw.zfill(3) if len(raw) <= 3 else raw
        if padded in _MAIN_INSURANCE_CODES:
            return padded
        if raw in _MAIN_INSURANCE_CODES:
            return raw
    if "ΝΑΤ" in text or "ΝΑΥΤΙΚ" in text:
        return "002"
    if "ΤΡΑΠΕΖ" in text:
        return "003"
    if "ΕΦΚΑ" in text or "ΙΚΑ" in text or "ΗΛΕΚΤΡΟΝΙΚ" in text:
        return "001"
    return default


def normalize_epikourikiki_kod(
    value: Any, *, default: str = DEFAULT_EPIKOURIKIKI
) -> str:
    """Κωδικός ForeisEpikourikisAsfalisis (π.χ. 001 από «001-ΚΛΑΔΟΣ…»)."""
    text = str(value or "").strip().upper()
    if not text:
        return default
    m = re.match(r"^(\d{1,10})", text)
    if m and m.group(1) != "0":
        raw = m.group(1)
        padded = raw.zfill(3) if len(raw) <= 3 else raw
        if padded in _SUPPLEMENTARY_INSURANCE_CODES:
            return padded
        if raw in _SUPPLEMENTARY_INSURANCE_CODES:
            return raw
    if "ΤΕΚΑ" in text:
        return "002"
    if "ΚΕΑΝ" in text or "ΝΑΥΤΙΚ" in text:
        return "010"
    if "ΕΦΚΑ" in text or "ΚΛΑΔΟΣ ΕΠΙΚΟΥΡΙΚΗΣ" in text:
        return "001"
    return default


def epikourikiki_codes_from_data(data: dict[str, Any]) -> list[str]:
    """Λίστα κωδικών επικουρικής από draft/EX_BASE_05 (τουλάχιστον ένας)."""
    raw = (
        data.get("epikourikiki_kod")
        or data.get("epikourikiki_codes")
        or data.get("f_epikouriki_kod")
        or data.get("EpikourikiAsfalisi")
    )
    codes: list[str] = []
    if isinstance(raw, list):
        codes = [normalize_epikourikiki_kod(c) for c in raw if str(c or "").strip()]
    elif raw is not None and str(raw).strip():
        parts = re.split(r"[,;|]+", str(raw))
        codes = [normalize_epikourikiki_kod(p) for p in parts if str(p or "").strip()]
    if not codes:
        codes = [DEFAULT_EPIKOURIKIKI]
    seen: set[str] = set()
    out: list[str] = []
    for code in codes:
        if code not in seen:
            seen.add(code)
            out.append(code)
    return out


def normalize_identity_type(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return DEFAULT_IDENTITY_TYPE
    # Παλιό λάθος «ΔAT» (Latin A/T) → σωστό ελληνικό ΔΑΤ.
    if raw in ("ΔAT", "DAT", "ΔΑT", "ΔAΤ"):
        return DEFAULT_IDENTITY_TYPE
    if raw in _IDENTITY_CODES:
        return raw
    # Παλιό default / ελεύθερο κείμενο → αστυνομική ταυτότητα.
    upper = raw.upper().replace(" ", "")
    if upper in ("ΑΤ", "AT", "ΔΑΤ", "DAT") or "ΑΣΤΥΝΟΜ" in upper:
        return DEFAULT_IDENTITY_TYPE
    for row in IDENTITY_DOCUMENT_TYPES:
        if row["label"] in raw.upper() or raw.upper() in row["label"]:
            return row["code"]
    return raw[:10]


def personal_fields_from_ex_base_05(item: dict[str, Any]) -> dict[str, Any]:
    """Χαρτογράφηση EX_BASE_05 Cur[] → πεδία φόρμας WebMA."""
    out: dict[str, Any] = {}
    mapping = [
        ("eponymo", ("Eponimo", "Eponymo", "eponymo")),
        ("onoma", ("Onoma", "onoma")),
        ("onoma_patros", ("OnomaPatera", "onoma_patros")),
        ("onoma_mitros", ("OnomaMiteras", "onoma_mitros")),
        ("birthdate", ("BirthDate", "birthdate")),
        ("sex", ("Sex", "sex")),
        ("yphkoothta", ("Nationality", "yphkoothta")),
        ("typos_taytothtas", ("TyposTaytotitas", "typos_taytothtas")),
        ("ar_taytothtas", ("ArTaytotitas", "ar_taytothtas")),
        ("ekdousa_arxh", ("EkdousaArxi", "ekdousa_arxh")),
        ("date_ekdosis", ("DateEkdosis", "date_ekdosis")),
        ("date_ekdosis_lixi", ("DateEkdosisLixi", "DateLixis", "date_ekdosis_lixi")),
        ("amka", ("Amka", "amka")),
        ("amika", ("AmIka", "amika")),
        ("code_anergias", ("CodeAnergias", "code_anergias")),
        ("ar_vivliou_anilikou", ("ArVivliouAnilikou", "ar_vivliou_anilikou")),
        ("marital_status", ("MaritalStatus", "marital_status")),
        ("arithmos_teknon", ("NumChildren", "arithmos_teknon")),
        ("epipedo_morfosis", ("EpipedoMorfosis", "epipedo_morfosis")),
        ("specialty", ("Eidikothta", "specialty")),
        ("step92", ("Step", "step92")),
        ("salary", ("Apodoxes", "salary")),
        ("hourly_wage", ("HourApodoxes", "hourly_wage")),
        ("weekly_hours", ("WeekHours", "weekly_hours")),
        ("fulltime_contract_weekly_hours", ("FullEmploymentHours", "fulltime_contract_weekly_hours")),
        ("weekly_work_days", ("WeekDays", "weekly_work_days")),
        ("employment_relation", ("SxesiApasxolisis", "employment_relation")),
        ("regime", ("KathestosApasxolisis", "regime")),
        ("characterization", ("asXaraktirismos", "characterization")),
        ("prior_service", ("Proipiresia", "prior_service")),
        ("break_minutes", ("DialeimmaMinutes", "Dialeimma", "break_minutes")),
        ("break_in_work", ("DialeimmaEntosWrariou", "break_in_work")),
        ("flex_arrival_minutes", ("EueliktoWrario", "flex_arrival_minutes")),
        ("working_card", ("WorkingCard", "working_card")),
        (
            "working_time_digital_organization",
            ("WorkingTimeDigitalOrganization", "working_time_digital_organization"),
        ),
        ("kyria_asfalish", ("KyriaAsfalisi", "kyria_asfalish")),
        ("epikourikiki_kod", ("EpikourikiAsfalisi", "epikourikiki_kod")),
        (
            "prosthetes_asfalistikes_paroxes",
            ("ProsthetesAsfalistikesParoxes", "prosthetes_asfalistikes_paroxes"),
        ),
        ("xronos_katabolhs", ("XronosKatabolisApodoxwn", "xronos_katabolhs")),
        ("eidos_dieuthethshs", ("Dieythetisi", "eidos_dieuthethshs")),
        ("topos_ergasias", ("ToposErgasias", "topos_ergasias")),
        (
            "topos_ergasias_comments",
            ("ToposErgasiasComments", "topos_ergasias_comments"),
        ),
        (
            "efarmostea_sillogiki_simbasi",
            ("EfarmosteaSyllogikiSymbasi", "efarmostea_sillogiki_simbasi"),
        ),
        (
            "efarmostea_sillogiki_simbasi_comments",
            ("EfarmosteaSyllogikiSymbasiComments", "efarmostea_sillogiki_simbasi_comments"),
        ),
        ("ipoxreotiki_katartisi", ("IpoxreotikiKatartisi", "ipoxreotiki_katartisi")),
        (
            "mh_problepsimo_programma",
            ("MhProblepsimoProgrammaErgasias", "mh_problepsimo_programma"),
        ),
        ("trial_period", ("TrialPeriod", "trial_period")),
        ("responsible_position", ("ResponsiblePosition", "responsible_position")),
    ]
    for target, keys in mapping:
        for key in keys:
            if key in item and item.get(key) is not None and str(item.get(key)).strip() != "":
                out[target] = item.get(key)
                break
    if "typos_taytothtas" in out:
        out["typos_taytothtas"] = normalize_identity_type(out["typos_taytothtas"])
    if "kyria_asfalish" in out:
        out["kyria_asfalish"] = normalize_kyria_asfalish(out["kyria_asfalish"])
    if "epikourikiki_kod" in out:
        out["epikourikiki_kod"] = normalize_epikourikiki_kod(out["epikourikiki_kod"])
    if "birthdate" in out:
        out["birthdate"] = _ergani_date(out["birthdate"])
    if "date_ekdosis" in out:
        out["date_ekdosis"] = _ergani_date(out["date_ekdosis"])
    if "date_ekdosis_lixi" in out:
        out["date_ekdosis_lixi"] = _ergani_date(out["date_ekdosis_lixi"])
    if "yphkoothta" in out:
        yph = _digits(out["yphkoothta"], max_len=3)
        if yph:
            out["yphkoothta"] = yph.zfill(3)
    if "epipedo_morfosis" in out:
        epi = _digits(str(out["epipedo_morfosis"]).split("-", 1)[0], max_len=10)
        if epi:
            out["epipedo_morfosis"] = epi
    if "sex" in out:
        out["sex"] = _enum_digit_code(out["sex"], allowed={"0", "1"}) or str(out["sex"]).strip()
    if "marital_status" in out:
        out["marital_status"] = _enum_digit_code(
            out["marital_status"], allowed={"0", "1", "2", "3"}, default="0"
        )
    if "employment_relation" in out:
        mapped = map_employment_relation(out["employment_relation"])
        if mapped:
            out["employment_relation"] = mapped
    if "regime" in out:
        mapped = map_regime(out["regime"])
        if mapped:
            out["regime"] = mapped
    if "characterization" in out:
        mapped = map_characterization(out["characterization"])
        if mapped:
            out["characterization"] = mapped
    if "weekly_work_days" in out:
        mapped = map_week_days(out["weekly_work_days"])
        if mapped:
            out["weekly_work_days"] = mapped
    if "working_card" in out:
        out["working_card"] = _enum_digit_code(
            out["working_card"], allowed={"0", "1"}, default="1"
        )
    if "working_time_digital_organization" in out:
        out["working_time_digital_organization"] = _enum_digit_code(
            out["working_time_digital_organization"], allowed={"0", "1"}, default="1"
        )
    if "break_in_work" in out:
        mapped = map_yes_no(out["break_in_work"])
        if mapped is not None:
            out["break_in_work"] = mapped
        else:
            out["break_in_work"] = _enum_digit_code(
                out["break_in_work"], allowed={"0", "1"}, default="0"
            )
    if "topos_ergasias" in out:
        out["topos_ergasias"] = normalize_topos_ergasias(out["topos_ergasias"])
    if "efarmostea_sillogiki_simbasi" in out:
        out["efarmostea_sillogiki_simbasi"] = normalize_yes_no_flag(
            out["efarmostea_sillogiki_simbasi"], default="0"
        )
    if "ipoxreotiki_katartisi" in out:
        out["ipoxreotiki_katartisi"] = normalize_yes_no_flag(
            out["ipoxreotiki_katartisi"], default="0"
        )
    if "mh_problepsimo_programma" in out:
        out["mh_problepsimo_programma"] = normalize_yes_no_flag(
            out["mh_problepsimo_programma"], default="0"
        )
    if "trial_period" in out:
        out["trial_period"] = normalize_yes_no_flag(out["trial_period"], default="0")
    return out


def draft_from_contract(
    contract: dict[str, Any] | None,
    *,
    branch_aa: str,
    employee_afm: str,
) -> dict[str, Any]:
    row = contract or {}
    afm = norm_afm(str(row.get("employee_afm") or employee_afm))
    out: dict[str, Any] = {
        "employee_afm": afm,
        "eponymo": str(row.get("eponymo") or "").strip(),
        "onoma": str(row.get("onoma") or "").strip(),
        "onoma_patros": str(row.get("onoma_patros") or "").strip(),
        "onoma_mitros": str(row.get("onoma_mitros") or "").strip(),
        "birthdate": (
            _ergani_date(row.get("birthdate"))
            if str(row.get("birthdate") or "").strip()
            else ""
        ),
        "sex": str(row.get("sex") or "").strip(),
        "yphkoothta": (
            (_digits(row.get("yphkoothta"), max_len=3) or "025").zfill(3)
            if str(row.get("yphkoothta") or "").strip()
            else "025"
        ),
        "typos_taytothtas": normalize_identity_type(row.get("typos_taytothtas")),
        "ar_taytothtas": str(row.get("ar_taytothtas") or "").strip(),
        "ekdousa_arxh": str(row.get("ekdousa_arxh") or "").strip(),
        "date_ekdosis": (
            _ergani_date(row.get("date_ekdosis"))
            if str(row.get("date_ekdosis") or "").strip()
            else ""
        ),
        "date_ekdosis_lixi": (
            _ergani_date(row.get("date_ekdosis_lixi"))
            if str(row.get("date_ekdosis_lixi") or "").strip()
            else ""
        ),
        "marital_status": _enum_digit_code(
            row.get("marital_status"), allowed={"0", "1", "2", "3"}, default="0"
        )
        or "0",
        "arithmos_teknon": str(row.get("arithmos_teknon") or "0").strip() or "0",
        "epipedo_morfosis": (
            _digits(str(row.get("epipedo_morfosis") or "0").split("-", 1)[0], max_len=10)
            or "0"
        ),
        "amka": str(row.get("amka") or "").strip(),
        "amika": str(row.get("amika") or "").strip(),
        "branch_aa": str(row.get("branch_aa") or branch_aa or "0").strip() or "0",
        "change_date": datetime.now(tz_athens()).strftime("%d/%m/%Y"),
        "change_types": [],
        "basics_acceptance": "1",
        "specialty": str(row.get("specialty") or "").strip(),
        "specialty_code": specialty_code(row.get("specialty"), row.get("step92")),
        "step92": str(row.get("step92") or "").strip(),
        "salary": str(row.get("salary") or "").strip(),
        "hourly_wage": str(row.get("hourly_wage") or "").strip(),
        "weekly_hours": str(row.get("weekly_hours") or "").strip(),
        "total_weekly_hours": str(row.get("total_weekly_hours") or "").strip(),
        "fulltime_contract_weekly_hours": str(
            row.get("fulltime_contract_weekly_hours") or ""
        ).strip(),
        "weekly_work_days": str(row.get("weekly_work_days") or "").strip(),
        "employment_relation": str(row.get("employment_relation") or "").strip(),
        "regime": str(row.get("regime") or "").strip(),
        "characterization": (
            map_characterization(row.get("characterization"))
            or str(row.get("characterization") or "").strip()
        ),
        "fixed_term_from": str(row.get("fixed_term_from") or "").strip(),
        "fixed_term_to": str(row.get("fixed_term_to") or "").strip(),
        "prior_service": str(row.get("prior_service") or "0").strip() or "0",
        "break_minutes": row.get("break_minutes") if row.get("break_minutes") is not None else "0",
        "break_in_work": row.get("break_in_work") if row.get("break_in_work") is not None else "0",
        "flex_arrival_minutes": (
            row.get("flex_arrival_minutes")
            if row.get("flex_arrival_minutes") is not None
            else "0"
        ),
        "working_time_digital_organization": str(
            row.get("working_time_digital_organization") or "1"
        ),
        "working_card": str(row.get("working_card") or "1"),
        "kyria_asfalish": normalize_kyria_asfalish(row.get("kyria_asfalish")),
        "epikourikiki_kod": normalize_epikourikiki_kod(row.get("epikourikiki_kod")),
        "prosthetes_asfalistikes_paroxes": str(
            row.get("prosthetes_asfalistikes_paroxes") or ""
        ).strip(),
        "xronos_katabolhs": str(row.get("xronos_katabolhs") or "").strip() or "Μηνιαίως",
        "eidos_dieuthethshs": _enum_digit_code(
            row.get("eidos_dieuthethshs"), allowed={"0", "1", "2"}, default=DEFAULT_DIEUTHETISI
        )
        or DEFAULT_DIEUTHETISI,
        "topos_ergasias": normalize_topos_ergasias(row.get("topos_ergasias")),
        "topos_ergasias_comments": str(row.get("topos_ergasias_comments") or "").strip(),
        "efarmostea_sillogiki_simbasi": normalize_yes_no_flag(
            row.get("efarmostea_sillogiki_simbasi"), default="0"
        ),
        "efarmostea_sillogiki_simbasi_comments": str(
            row.get("efarmostea_sillogiki_simbasi_comments") or ""
        ).strip(),
        "ipoxreotiki_katartisi": normalize_yes_no_flag(
            row.get("ipoxreotiki_katartisi"), default="0"
        ),
        "mh_problepsimo_programma": normalize_yes_no_flag(
            row.get("mh_problepsimo_programma"), default="0"
        ),
        "trial_period": normalize_yes_no_flag(row.get("trial_period"), default="0"),
        "topothetisioaed": normalize_yes_no_flag(row.get("topothetisioaed"), default="0"),
        "comments": "",
        "change_types_catalog": CHANGE_TYPES,
        "basics_acceptance_catalog": BASICS_ACCEPTANCE,
        "identity_document_types": IDENTITY_DOCUMENT_TYPES,
        "main_insurance_funds": MAIN_INSURANCE_FUNDS,
        "supplementary_insurance_funds": SUPPLEMENTARY_INSURANCE_FUNDS,
        "dieuthetisi_types": DIEUTHETISI_TYPES,
        "submission_code": SUBMISSION_CODE_WEB_MA,
    }
    char = out["characterization"] or "0"
    aligned = align_gross_pay_with_ergani_formula(
        week_hours=out["weekly_hours"] or out["total_weekly_hours"],
        hourly_wage=out["hourly_wage"],
        characterization=char,
        current_salary=out["salary"],
    )
    if aligned:
        out["salary"] = aligned
    return out

def _eu_float(value: Any) -> float | None:
    raw = str(value or "").strip().replace("€", "").replace(" ", "")
    if not raw:
        return None
    if "," in raw and "." in raw:
        raw = raw.replace(".", "").replace(",", ".")
    elif "," in raw:
        raw = raw.replace(",", ".")
    try:
        return float(raw)
    except ValueError:
        return None


def align_gross_pay_with_ergani_formula(
    *,
    week_hours: Any,
    hourly_wage: Any,
    characterization: str,
    current_salary: Any = None,
) -> str | None:
    """
    Μεικτές = εβδ. ώρες × (4,333 εργάτης / 4,166 υπάλληλος) × ωρομίσθιο.
    Επιστρέφει ποσό σε μορφή Ergani ή None αν δεν μπορεί να υπολογιστεί.
    """
    wh = _eu_float(week_hours)
    hp = _eu_float(hourly_wage)
    if wh is None or hp is None or hp <= 0 or wh <= 0:
        return _money(current_salary) if current_salary is not None else None
    factor = 4.333 if str(characterization) == "0" else 4.166
    return _money(f"{wh * factor * hp:.2f}")


def _require_text(data: dict[str, Any], *keys: str, label: str, max_len: int) -> str:
    for key in keys:
        text = str(data.get(key) or "").strip()
        if text:
            return text[:max_len]
    raise WorkCardPayloadError(f"Λείπει {label}")


def build_web_ma_payload(
    data: dict[str, Any],
    *,
    branch_aa: str | None = None,
) -> dict[str, Any]:
    """
    Σώμα WebMA με όλα τα XSD-υποχρεωτικά πεδία στη σωστή σειρά.

    Υποχρεωτικά βάσει Lookup schema (minLength>=1 ή pattern χωρίς κενό):
    παράρτημα, ταυτότητα εργαζομένου, ΑΦΜ, ειδικότητα, αποδοχές/ώρες κ.ά.
    """
    afm = norm_afm(str(data.get("employee_afm") or data.get("f_afm") or ""))
    if not afm or len(afm) != 9:
        raise WorkCardPayloadError("Λείπει έγκυρο ΑΦΜ εργαζομένου")

    eponymo = _require_text(data, "eponymo", "f_eponymo", label="επώνυμο", max_len=50)
    onoma = _require_text(data, "onoma", "f_onoma", label="όνομα", max_len=30)
    father = _require_text(
        data, "onoma_patros", "f_onoma_patros", label="όνομα πατρός", max_len=30
    )
    mother = _require_text(
        data, "onoma_mitros", "f_onoma_mitros", label="όνομα μητρός", max_len=30
    )
    birth_raw = str(data.get("birthdate") or data.get("f_birthdate") or "").strip()
    if not birth_raw:
        raise WorkCardPayloadError("Λείπει ημερομηνία γέννησης")
    birthdate = _ergani_date(birth_raw)

    sex = _enum_digit_code(
        data.get("sex") or data.get("f_sex"), allowed={"0", "1"}
    )
    if sex not in ("0", "1"):
        raise WorkCardPayloadError("Επιλέξτε φύλο")

    yphkoothta = _digits(
        data.get("yphkoothta") or data.get("f_yphkoothta") or "025", max_len=3
    ) or "025"
    id_type = normalize_identity_type(
        data.get("typos_taytothtas") or data.get("f_typos_taytothtas")
    )
    id_no = _require_text(
        data, "ar_taytothtas", "f_ar_taytothtas", label="αριθμό ταυτότητας", max_len=20
    )
    amka = _digits(data.get("amka") or data.get("f_amka"), max_len=20) or ""
    if not amka or len(amka) < 11:
        raise WorkCardPayloadError("Λείπει έγκυρο ΑΜΚΑ εργαζομένου (11 ψηφία)")
    amika = _digits(data.get("amika") or data.get("f_amika"), max_len=20) or ""

    raw_types = data.get("change_types") or data.get("types") or []
    if isinstance(raw_types, str):
        raw_types = [raw_types]
    types = [str(code).strip().zfill(3)[-3:] for code in raw_types if str(code).strip()]
    types = [code for code in types if code in _CHANGE_CODES]
    if not types:
        raise WorkCardPayloadError("Επιλέξτε τουλάχιστον έναν τύπο μεταβολής")

    acceptance = str(data.get("basics_acceptance") or data.get("f_basics_acceptance") or "1").strip()
    if acceptance not in ("0", "1", "2"):
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

    change_date = _ergani_date(data.get("change_date") or data.get("f_date_metabolhs"))
    aa = str(
        data.get("branch_aa")
        or data.get("f_aa_pararthmatos")
        or branch_aa
        or "0"
    ).strip() or "0"

    rel_protocol = str(data.get("f_rel_protocol") or data.get("rel_protocol") or "").strip() or " "
    rel_date = str(data.get("f_rel_date") or data.get("rel_date") or "").strip() or " "

    sepe = str(
        data.get("f_ypiresia_sepe") or data.get("sepe_code") or data.get("ypiresia_sepe") or ""
    ).strip()
    oaed = str(
        data.get("f_ypiresia_oaed") or data.get("oaed_code") or data.get("ypiresia_oaed") or ""
    ).strip()
    kad = str(
        data.get("f_kad_pararthmatos") or data.get("kad_code") or data.get("kad") or ""
    ).strip()
    kallikratis = str(
        data.get("f_kallikratis_pararthmatos")
        or data.get("kallikratis_code")
        or data.get("kallikratis")
        or ""
    ).strip()
    if not sepe or not oaed or not kad or not kallikratis:
        raise WorkCardPayloadError(
            "Λείπουν κωδικοί παραρτήματος (ΣΕΠΕ / ΟΑΕΔ / ΚΑΔ / Καλλικράτης) στο κατάστημα"
        )

    eid = specialty_code(
        data.get("specialty_code") or data.get("f_eidikothta"),
        data.get("step92") or data.get("specialty"),
    )
    if not eid:
        raise WorkCardPayloadError("Λείπει κωδικός ειδικότητας")
    salary = _money(data.get("salary") or data.get("f_apodoxes"))
    if not salary:
        raise WorkCardPayloadError("Λείπουν μεικτές αποδοχές")
    week_hours = _hours(
        data.get("weekly_hours") or data.get("total_weekly_hours") or data.get("f_week_hours")
    )
    if not week_hours:
        raise WorkCardPayloadError("Λείπουν ώρες εβδομαδιαίως")
    full_hours = _hours(
        data.get("fulltime_contract_weekly_hours") or data.get("f_full_employment_hours")
    ) or week_hours
    hour_pay = _money(data.get("hourly_wage") or data.get("f_hour_apodoxes")) or "0,00"

    relation = map_employment_relation(
        data.get("employment_relation") or data.get("f_sxeshapasxolisis")
    ) or "0"
    regime = map_regime(data.get("regime") or data.get("f_kathestosapasxolisis")) or "0"
    characterization = map_characterization(
        data.get("characterization") or data.get("f_xaraktirismos")
    ) or "0"
    week_days = map_week_days(data.get("weekly_work_days") or data.get("f_week_days")) or "5"

    fixed_from_raw = str(data.get("fixed_term_from") or data.get("f_orismenou_apo") or "").strip()
    fixed_to_raw = str(data.get("fixed_term_to") or data.get("f_orismenou_ews") or "").strip()
    if relation == "1":
        if not fixed_from_raw or not fixed_to_raw:
            raise WorkCardPayloadError(
                "Για σχέση ορισμένου χρόνου απαιτούνται ημερομηνίες από / έως"
            )

    # Ergani ελέγχει αυστηρά τον τύπο μεικτών αποδοχών.
    aligned = align_gross_pay_with_ergani_formula(
        week_hours=week_hours,
        hourly_wage=hour_pay,
        characterization=characterization,
        current_salary=salary,
    )
    if aligned:
        salary = aligned

    xronos_katabolhs = str(
        data.get("xronos_katabolhs") or data.get("f_xronos_katabolhs") or ""
    ).strip() or "Μηνιαίως"

    borrow_type = str(data.get("borrow_type") or data.get("f_borrow_type") or "").strip()
    if borrow_type not in ("", "0", "1"):
        borrow_type = ""

    values: dict[str, Any] = {
        "f_aa_pararthmatos": aa,
        "f_rel_protocol": rel_protocol,
        "f_rel_date": rel_date,
        "f_ypiresia_sepe": sepe,
        "f_ypiresia_oaed": oaed,
        "f_kad_pararthmatos": kad,
        "f_kallikratis_pararthmatos": kallikratis,
        "f_eponymo": eponymo,
        "f_onoma": onoma,
        "f_onoma_patros": father,
        "f_onoma_mitros": mother,
        "f_birthdate": birthdate,
        "f_sex": sex,
        "f_yphkoothta": yphkoothta,
        "f_typos_taytothtas": id_type[:10],
        "f_ar_taytothtas": id_no,
        # XSD sequence: εκδούσα αρχή + ημερομηνίες πριν το marital / άδειες διαμονής.
        "f_ekdousa_arxh": (
            str(data.get("ekdousa_arxh") or data.get("f_ekdousa_arxh") or "").strip() or " "
        )[:50],
        "f_date_ekdosis": (
            _ergani_date(data.get("date_ekdosis") or data.get("f_date_ekdosis"))
            if str(data.get("date_ekdosis") or data.get("f_date_ekdosis") or "").strip()
            else " "
        ),
        "f_date_ekdosis_lixi": (
            _ergani_date(data.get("date_ekdosis_lixi") or data.get("f_date_ekdosis_lixi"))
            if str(data.get("date_ekdosis_lixi") or data.get("f_date_ekdosis_lixi") or "").strip()
            else " "
        ),
        # XSD sequence: πλήρες block αδειών διαμονής πριν το marital (0 = όχι).
        "f_res_permit_inst": _res_permit_flag(
            data.get("res_permit_inst") or data.get("f_res_permit_inst")
        ),
        "f_res_permit_inst_type": str(
            data.get("res_permit_inst_type") or data.get("f_res_permit_inst_type") or ""
        ).strip(),
        "f_res_permit_inst_ar": str(
            data.get("res_permit_inst_ar") or data.get("f_res_permit_inst_ar") or ""
        ).strip()[:20],
        "f_res_permit_inst_lixi": (
            _ergani_date(data.get("res_permit_inst_lixi") or data.get("f_res_permit_inst_lixi"))
            if str(
                data.get("res_permit_inst_lixi") or data.get("f_res_permit_inst_lixi") or ""
            ).strip()
            else " "
        ),
        "f_res_permit_ap": _res_permit_flag(
            data.get("res_permit_ap") or data.get("f_res_permit_ap")
        ),
        "f_res_permit_ap_type": str(
            data.get("res_permit_ap_type") or data.get("f_res_permit_ap_type") or ""
        ).strip(),
        "f_res_permit_ap_ar": str(
            data.get("res_permit_ap_ar") or data.get("f_res_permit_ap_ar") or ""
        ).strip()[:20],
        "f_res_permit_ap_lixi": (
            _ergani_date(data.get("res_permit_ap_lixi") or data.get("f_res_permit_ap_lixi"))
            if str(
                data.get("res_permit_ap_lixi") or data.get("f_res_permit_ap_lixi") or ""
            ).strip()
            else " "
        ),
        "f_res_permit_visa": _res_permit_flag(
            data.get("res_permit_visa") or data.get("f_res_permit_visa")
        ),
        "f_res_permit_visa_ar": str(
            data.get("res_permit_visa_ar") or data.get("f_res_permit_visa_ar") or ""
        ).strip()[:20],
        "f_res_permit_visa_from": (
            _ergani_date(data.get("res_permit_visa_from") or data.get("f_res_permit_visa_from"))
            if str(
                data.get("res_permit_visa_from") or data.get("f_res_permit_visa_from") or ""
            ).strip()
            else " "
        ),
        "f_res_permit_visa_to": (
            _ergani_date(data.get("res_permit_visa_to") or data.get("f_res_permit_visa_to"))
            if str(
                data.get("res_permit_visa_to") or data.get("f_res_permit_visa_to") or ""
            ).strip()
            else " "
        ),
        "f_marital_status": _enum_digit_code(
            data.get("marital_status") or data.get("f_marital_status"),
            allowed={"0", "1", "2", "3"},
            default="0",
        )
        or "0",
        "f_arithmos_teknon": _digits(
            data.get("arithmos_teknon") or data.get("f_arithmos_teknon") or "0",
            max_len=2,
        )
        or "0",
        "f_afm": afm,
        "f_doy": str(data.get("doy") or data.get("f_doy") or "").strip() or " ",
        "f_amika": amika,
        "f_amka": amka,
        "f_code_anergias": str(
            data.get("code_anergias") or data.get("f_code_anergias") or ""
        ).strip()[:20],
        "f_ar_vivliou_anilikou": str(
            data.get("ar_vivliou_anilikou") or data.get("f_ar_vivliou_anilikou") or ""
        ).strip()[:20],
        "f_epipedo_morfosis": _digits(
            data.get("epipedo_morfosis") or data.get("f_epipedo_morfosis") or "0",
            max_len=10,
        )
        or "0",
        "f_date_metabolhs": change_date,
        "f_eidos_dieuthethshs": _enum_digit_code(
            data.get("eidos_dieuthethshs") or data.get("f_eidos_dieuthethshs"),
            allowed={"0", "1", "2"},
            default="2",
        )
        or "2",
        "f_eidos_dieuthethshs_comments": str(
            data.get("eidos_dieuthethshs_comments")
            or data.get("f_eidos_dieuthethshs_comments")
            or ""
        ).strip()[:200],
        "f_periodos_anaforas_from": (
            _ergani_date(data.get("periodos_anaforas_from") or data.get("f_periodos_anaforas_from"))
            if str(
                data.get("periodos_anaforas_from") or data.get("f_periodos_anaforas_from") or ""
            ).strip()
            else " "
        ),
        "f_periodos_anaforas_to": (
            _ergani_date(data.get("periodos_anaforas_to") or data.get("f_periodos_anaforas_to"))
            if str(
                data.get("periodos_anaforas_to") or data.get("f_periodos_anaforas_to") or ""
            ).strip()
            else " "
        ),
        "f_eidikothta": eid,
        "f_eidikothta_anal": str(
            data.get("specialty") or data.get("f_eidikothta_anal") or ""
        ).strip()[:255],
        "f_proipiresia": _digits(data.get("prior_service") or data.get("f_proipiresia") or "0", max_len=3)
        or "0",
        "f_apodoxes": salary,
        "f_hour_apodoxes": hour_pay,
        "f_xronos_katabolhs": xronos_katabolhs[:200],
        "f_topos_ergasias": normalize_topos_ergasias(
            data.get("topos_ergasias") or data.get("f_topos_ergasias")
        ),
        "f_topos_ergasias_comments": str(
            data.get("topos_ergasias_comments")
            or data.get("f_topos_ergasias_comments")
            or ""
        ).strip()[:200],
        "f_sxeshapasxolisis": relation,
        "f_orismenou_apo": _ergani_date(fixed_from_raw) if relation == "1" and fixed_from_raw else " ",
        "f_orismenou_ews": _ergani_date(fixed_to_raw) if relation == "1" and fixed_to_raw else " ",
        "f_kathestosapasxolisis": regime,
        "f_xaraktirismos": characterization,
        "f_efarmostea_sillogiki_simbasi": normalize_yes_no_flag(
            data.get("efarmostea_sillogiki_simbasi")
            or data.get("f_efarmostea_sillogiki_simbasi"),
            default="0",
        ),
        "f_efarmostea_sillogiki_simbasi_comments": str(
            data.get("efarmostea_sillogiki_simbasi_comments")
            or data.get("f_efarmostea_sillogiki_simbasi_comments")
            or ""
        ).strip()[:200],
        "f_kyria_asfalish": normalize_kyria_asfalish(
            data.get("kyria_asfalish") or data.get("f_kyria_asfalish")
        ),
        "f_prosthetes_asfalistikes_paroxes": str(
            data.get("prosthetes_asfalistikes_paroxes")
            or data.get("f_prosthetes_asfalistikes_paroxes")
            or ""
        ).strip()[:200],
        "f_ipoxreotiki_katartisi": normalize_yes_no_flag(
            data.get("ipoxreotiki_katartisi") or data.get("f_ipoxreotiki_katartisi"),
            default="0",
        ),
        "f_working_time_digital_organization": str(
            data.get("working_time_digital_organization") or "1"
        ),
        "f_mh_problepsimo_programma": normalize_yes_no_flag(
            data.get("mh_problepsimo_programma")
            or data.get("f_mh_problepsimo_programma"),
            default="0",
        ),
        "f_week_hours": week_hours,
        "f_full_employment_hours": full_hours,
        "f_week_days": week_days,
        "f_euelikto_wrario_minutes": _digits(
            data.get("flex_arrival_minutes") or data.get("f_euelikto_wrario_minutes") or "0",
            max_len=3,
        )
        or "0",
        "f_working_card": str(data.get("working_card") or "1"),
        "f_dialeimma_minutes": _digits(
            data.get("break_minutes") or data.get("f_dialeimma_minutes") or "0",
            max_len=3,
        )
        or "0",
        "f_dialeimma_entos_wrariou": map_yes_no(data.get("break_in_work"))
        or str(data.get("f_dialeimma_entos_wrariou") or "0"),
        "f_topothetisioaed": normalize_yes_no_flag(
            data.get("topothetisioaed") or data.get("f_topothetisioaed"),
            default="0",
        ),
        "f_trial_period": normalize_yes_no_flag(
            data.get("trial_period") or data.get("f_trial_period"),
            default="0",
        ),
        "f_borrow_type": borrow_type,
        "f_borrow_company_afm": (
            norm_afm(str(data.get("borrow_company_afm") or data.get("f_borrow_company_afm") or ""))
            if borrow_type in ("0", "1")
            else ""
        ),
        "f_borrow_company_eponimia": (
            str(
                data.get("borrow_company_eponimia")
                or data.get("f_borrow_company_eponimia")
                or ""
            ).strip()[:230]
            if borrow_type in ("0", "1")
            else ""
        ),
        "f_epibolh_file": (
            str(data.get("f_epibolh_file") or "").strip()
            if ("014" in types or "015" in types)
            else ""
        ),
        "f_basics_acceptance": acceptance,
        "TypesMetabolon": {
            "TypesMetabolonMA": [{"f_typos_metabolhs": code} for code in types],
        },
        "Epikourikes": {
            "EpikourikesMA": [
                {"f_epikouriki_kod": code} for code in epikourikiki_codes_from_data(data)
            ],
        },
    }

    comments = str(data.get("comments") or "").strip()
    if comments:
        values["f_comments"] = comments[:100]
    # Πάντα ρητά: χωρίς PDF δεν αφήνουμε το default AA== (θεωρείται αρχείο).
    values["f_file"] = file_b64 if file_b64 else ""

    if "006" in types:
        values["f_sxeshapasxolisis"] = "0"
    if "007" in types:
        values["f_kathestosapasxolisis"] = "0"
    if "008" in types:
        values["f_kathestosapasxolisis"] = "1"
    if "014" in types or "015" in types:
        values["f_kathestosapasxolisis"] = "2"
    if "011" in types or "013" in types:
        values["f_working_card"] = "1"
        values["f_working_time_digital_organization"] = "1"
    if "016" in types and str(values.get("f_eidos_dieuthethshs") or "").strip() in ("", "2"):
        # Μεταβολή διευθέτησης: προεπιλογή ατομική συμφωνία αν δεν επιλέχθηκε ΝΑΙ.
        values["f_eidos_dieuthethshs"] = "1"
    if "016" not in types and not str(
        data.get("eidos_dieuthethshs") or data.get("f_eidos_dieuthethshs") or ""
    ).strip():
        values["f_eidos_dieuthethshs"] = "2"

    # Συμπλήρωση όλων των κενών της XSD sequence με ασφαλείς προεπιλογές.
    filled = dict(_XSD_SEQUENCE_DEFAULTS)
    filled.update({k: v for k, v in values.items() if v is not None})
    return {"AnaggeliesMA": {"AnaggeliaMA": [_ordered_anaggelia_ma(filled)]}}
