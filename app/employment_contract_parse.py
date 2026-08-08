"""Parse HTML στοιχείων σύμβασης από Mitroa/Ergazomenos.aspx."""

from __future__ import annotations

import re
from html import unescape
from typing import Any


_LABEL_MAP = {
    "Ειδικότητα": "specialty",
    "Χαρακτηρισμός": "characterization",
    "ΣΤΕΠ 92": "step92",
    "Ημέρες Εβδομαδιαίας απασχόλησης": "weekly_work_days",
    "Προϋπηρεσία(Έτη)": "prior_service",
    "Προϋπηρεσία": "prior_service",
    "Σχέση Απασχόλησης": "employment_relation",
    "Ορισμένου Χρόνου Ημ/νία Από": "fixed_term_from",
    "Ορισμένου Χρόνου Ημ/νία Έως": "fixed_term_to",
    "Καθεστώς": "regime",
    "Ώρες Εβδομαδιαίως": "weekly_hours",
    "Αποδοχές": "salary",
    "Ωρομίσθιο": "hourly_wage",
    "Συνολικές Ώρες Εβδομαδιαίως (Από όλες τις ενεργές σχέσεις εργασίας)": "total_weekly_hours",
    "Συνολικές Ώρες Εβδομαδιαίως": "total_weekly_hours",
    "Συμβατικές Εβδομαδιαίες Ώρες Πλήρους Απασχόλησης": "fulltime_contract_weekly_hours",
    "Διάλειμμα (σε λεπτά)": "break_minutes",
    "Διάλειμμα Εντός Ωραρίου": "break_in_work",
    "Ευέλικτη Προσέλευση (σε λεπτά)": "flex_arrival_minutes",
    "Ευέλικτη Προσέλευση": "flex_arrival_minutes",
    "Ημ/νία τελευταίας ενημέρωσης": "ergani_updated_at",
}


def _strip_tags(html: str) -> str:
    text = re.sub(r"<script[^>]*>.*?</script>", " ", html, flags=re.I | re.S)
    text = re.sub(r"<style[^>]*>.*?</style>", " ", text, flags=re.I | re.S)
    text = re.sub(r"<[^>]+>", " | ", text)
    text = unescape(text)
    text = re.sub(r"\s+", " ", text)
    return text


def _clean_value(raw: str) -> str:
    s = (raw or "").strip()
    s = s.replace("\xa0", " ").strip()
    if s.lower() in ("&nbsp;", "—", "-", "n/a"):
        return ""
    return s


def _parse_int_minutes(value: str) -> int | None:
    s = _clean_value(value)
    if not s:
        return None
    m = re.search(r"-?\d+", s.replace(",", "."))
    if not m:
        return None
    try:
        return int(float(m.group(0)))
    except ValueError:
        return None


def _parse_break_in_work(value: str) -> int | None:
    s = _clean_value(value).upper()
    if not s:
        return None
    if s in ("ΝΑΙ", "YES", "TRUE", "1"):
        return 1
    if s in ("ΟΧΙ", "NO", "FALSE", "0"):
        return 0
    return _parse_int_minutes(s)


def extract_labeled_values(html: str) -> dict[str, str]:
    """Εξαγωγή label → value από flattened HTML ( | separators)."""
    text = _strip_tags(html)
    out: dict[str, str] = {}
    # Sort longer labels first to avoid partial matches
    labels = sorted(_LABEL_MAP.keys(), key=len, reverse=True)
    for label in labels:
        # Label | | VALUE | |
        pat = re.escape(label) + r"\s*\|\s*\|\s*([^|]+?)\s*\|"
        m = re.search(pat, text)
        if not m:
            continue
        key = _LABEL_MAP[label]
        if key in out and out[key]:
            continue
        out[key] = _clean_value(m.group(1))
    return out


def extract_employee_name_afm(html: str) -> tuple[str, str, str]:
    """Επώνυμο, όνομα, ΑΦΜ από προσωπικά στοιχεία (πρώτες form-control spans)."""
    text = unescape(html)
    spans = re.findall(
        r'<span[^>]*class="[^"]*form-control[^"]*"[^>]*>([^<]*)</span>',
        text,
        re.I,
    )
    eponymo = _clean_value(spans[0]) if len(spans) > 0 else ""
    onoma = _clean_value(spans[1]) if len(spans) > 1 else ""
    afm = ""
    for s in spans:
        val = _clean_value(s)
        if re.fullmatch(r"\d{9}", val):
            afm = val
            break
    if not afm:
        m = re.search(r"[?&]afm=(\d{8,11})", text, re.I)
        if m:
            afm = m.group(1)[:9]
    return eponymo, onoma, afm


def parse_employment_contract_html(
    html: str,
    *,
    employee_afm: str | None = None,
) -> dict[str, Any]:
    fields = extract_labeled_values(html)
    eponymo, onoma, afm_from_page = extract_employee_name_afm(html)
    afm = (employee_afm or afm_from_page or "").strip()[:9]

    break_minutes = _parse_int_minutes(fields.get("break_minutes") or "")
    # Αν λείπει «Διάλειμμα (σε λεπτά)» αλλά υπάρχει γενικό «Διάλειμμα» ως λεπτά
    if break_minutes is None and fields.get("break_minutes"):
        break_minutes = _parse_int_minutes(fields["break_minutes"])

    return {
        "employee_afm": afm,
        "eponymo": eponymo or None,
        "onoma": onoma or None,
        "specialty": fields.get("specialty") or None,
        "characterization": fields.get("characterization") or None,
        "step92": fields.get("step92") or None,
        "weekly_work_days": fields.get("weekly_work_days") or None,
        "prior_service": fields.get("prior_service") or None,
        "employment_relation": fields.get("employment_relation") or None,
        "fixed_term_from": fields.get("fixed_term_from") or None,
        "fixed_term_to": fields.get("fixed_term_to") or None,
        "regime": fields.get("regime") or None,
        "weekly_hours": fields.get("weekly_hours") or None,
        "salary": fields.get("salary") or None,
        "hourly_wage": fields.get("hourly_wage") or None,
        "total_weekly_hours": fields.get("total_weekly_hours") or None,
        "fulltime_contract_weekly_hours": fields.get("fulltime_contract_weekly_hours")
        or None,
        "break_minutes": break_minutes,
        "break_in_work": _parse_break_in_work(fields.get("break_in_work") or ""),
        "flex_arrival_minutes": _parse_int_minutes(
            fields.get("flex_arrival_minutes") or ""
        ),
        "ergani_updated_at": fields.get("ergani_updated_at") or None,
        "source": "portal",
    }


def parse_search_select_ids(html: str) -> list[tuple[str, str, str]]:
    """Επιστρέφει [(ergodoti_id, employee_afm, stamp), ...] από κουμπιά Επιλογή."""
    text = unescape(html)
    out: list[tuple[str, str, str]] = []
    seen: set[str] = set()
    for m in re.finditer(r"Select\(\d+,\s*'([^']+)'\)", text):
        parts = m.group(1).split("|")
        if len(parts) < 2:
            continue
        ergodoti_id = parts[0].strip()
        afm = parts[1].strip()[:9]
        stamp = parts[2].strip() if len(parts) > 2 else ""
        if not afm or afm in seen:
            continue
        seen.add(afm)
        out.append((ergodoti_id, afm, stamp))
    return out
