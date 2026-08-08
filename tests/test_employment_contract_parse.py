"""Tests για parse στοιχείων σύμβασης από HTML Μητρώων."""

from __future__ import annotations

from app.employment_contract_parse import (
    parse_employment_contract_html,
    parse_search_select_ids,
)

SAMPLE_DETAIL = """
<html><body>
<span class="form-control">ΨΕΜΑΤΙΚΑΣ</span>
<span class="form-control">ΑΛΕΞΙΟΣ</span>
<span class="form-control">ΔΗΜΗΤΡΙΟΣ</span>
<span class="form-control">ΚΑΛΛΙΟΠΗ</span>
<span class="form-control">10/09/1984</span>
<span class="form-control">ΑΝΤΡΑΣ</span>
<span class="form-control">ΕΛΛΑΔΑ</span>
<span class="form-control">ΕΓΓΑΜΟΣ/Η</span>
<span class="form-control">1</span>
<span class="form-control"></span>
<span class="form-control"></span>
<span class="form-control">125485504</span>
<div id="EmploymentDataTab">
<label>Ειδικότητα</label><div>ΓΕΝΙΚΟΣ ΔΙΕΥΘΥΝΤΗΣ</div>
<label>Χαρακτηρισμός</label><div>ΥΠΑΛΛΗΛΟΣ</div>
<label>ΣΤΕΠ 92</label><div>ΓΕΝΙΚΟΙ ΔΙΕΥΘΥΝΤΕΣ ΕΣΤΙΑΤΟΡΙΩΝ</div>
<label>Ημέρες Εβδομαδιαίας απασχόλησης</label><div>5-ήμερη</div>
<label>Προϋπηρεσία(Έτη)</label><div>0</div>
<label>Σχέση Απασχόλησης</label><div>ΑΟΡΙΣΤΟΥ ΧΡΟΝΟΥ</div>
<label>Ορισμένου Χρόνου Ημ/νία Από</label><div></div>
<label>Ορισμένου Χρόνου Ημ/νία Έως</label><div></div>
<label>Καθεστώς</label><div>ΠΛΗΡΗΣ ΑΠΑΣΧΟΛΗΣΗ</div>
<label>Ώρες Εβδομαδιαίως</label><div>40,0</div>
<label>Αποδοχές</label><div>1400,00</div>
<label>Ωρομίσθιο</label><div>8,40</div>
<label>Συνολικές Ώρες Εβδομαδιαίως (Από όλες τις ενεργές σχέσεις εργασίας)</label><div>40,0</div>
<label>Συμβατικές Εβδομαδιαίες Ώρες Πλήρους Απασχόλησης</label><div>40</div>
</div>
<div id="SkillsTab">
<label>Διάλειμμα (σε λεπτά)</label><div>15</div>
<label>Διάλειμμα Εντός Ωραρίου</label><div>Ναι</div>
<label>Ευέλικτη Προσέλευση (σε λεπτά)</label><div>120</div>
<label>Ημ/νία τελευταίας ενημέρωσης</label><div>02/06/2025 00:00</div>
</div>
</body></html>
"""

SAMPLE_SEARCH = """
<input type="button" value="Επιλογή" onclick="if (Select(0, &#39;484893|125485504|27/10/2025&#39;) == false) return false;" />
<input type="button" value="Επιλογή" onclick="if (Select(1, '484893|162100972|24/4/2026') == false) return false;" />
"""


def test_parse_search_select_ids():
    rows = parse_search_select_ids(SAMPLE_SEARCH)
    assert rows[0] == ("484893", "125485504", "27/10/2025")
    assert rows[1][1] == "162100972"
    assert len(rows) == 2


def test_parse_employment_contract_html_fields():
    row = parse_employment_contract_html(SAMPLE_DETAIL)
    assert row["employee_afm"] == "125485504"
    assert row["eponymo"] == "ΨΕΜΑΤΙΚΑΣ"
    assert row["onoma"] == "ΑΛΕΞΙΟΣ"
    assert row["specialty"] == "ΓΕΝΙΚΟΣ ΔΙΕΥΘΥΝΤΗΣ"
    assert row["step92"] == "ΓΕΝΙΚΟΙ ΔΙΕΥΘΥΝΤΕΣ ΕΣΤΙΑΤΟΡΙΩΝ"
    assert row["weekly_hours"] == "40,0"
    assert row["salary"] == "1400,00"
    assert row["break_minutes"] == 15
    assert row["break_in_work"] == 1
    assert row["flex_arrival_minutes"] == 120
    assert row["ergani_updated_at"] == "02/06/2025 00:00"
