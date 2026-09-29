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
<label>Ημ/νία πρόσληψης</label><div>15/03/2020</div>
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
    assert row["hire_date"] == "15/03/2020"
    assert row["prior_service"] == "0"
    assert row["marital_status"] == "1"
    assert row["arithmos_teknon"] == "1"


def test_parse_employment_contract_html_amka_ama():
    html = SAMPLE_DETAIL.replace(
        "<label>Ημ/νία πρόσληψης</label><div>15/03/2020</div>",
        "<label>Ημ/νία πρόσληψης</label><div>15/03/2020</div>"
        "<label>ΑΜΚΑ</label><div>15039012345</div>"
        "<label>Α.Μ.Α.</label><div>1234567890</div>",
    )
    row = parse_employment_contract_html(html)
    assert row["amka"] == "15039012345"
    assert row["amika"] == "1234567890"


def test_map_marital_status_from_ergani_labels():
    from app.employment_contract_parse import map_marital_status

    assert map_marital_status("ΕΓΓΑΜΟΣ/Η") == "1"
    assert map_marital_status("ΑΓΑΜΟΣ/Η (0)") == "0"
    assert map_marital_status("2") == "2"
    assert map_marital_status("10/09/1984") == ""
    assert map_marital_status("") == ""


def test_parse_employment_contract_html_extracts_work_time_qr():
    html = SAMPLE_DETAIL.replace(
        "</body>",
        """
        <div id="DigitalWorkTimeTab">
          <h2>Ψηφιακή Οργάνωση Χρόνου Εργασίας</h2>
          <label>Κάρτα Εργασίας</label><div>Ναι</div>
          <img alt="QR Code" src="data:image/png;base64,QUJDRA==" />
        </div>
        </body>
        """,
    )
    row = parse_employment_contract_html(html)
    assert row["work_time_qr_src"] == "data:image/png;base64,QUJDRA=="


def test_parse_ergani_calendar_date_and_hire_field():
    from datetime import date

    from app.ergani_parse import hire_date_from_ergani_item, parse_ergani_calendar_date, parse_employees

    assert parse_ergani_calendar_date("15/3/2020") == date(2020, 3, 15)
    assert parse_ergani_calendar_date("2024-09-01T00:00:00+03:00") == date(2024, 9, 1)
    assert hire_date_from_ergani_item({"DateProslipsis": "01/06/2018"}) == date(2018, 6, 1)
    assert hire_date_from_ergani_item({"DateFrom": "2015-11-23T00:00:00+02:00"}) == date(2015, 11, 23)
    prefer = hire_date_from_ergani_item({
        "DateProslipsis": "2026-04-17T00:00:00+03:00",
        "DateFrom": "2020-01-01T00:00:00+02:00",
    })
    assert prefer == date(2026, 4, 17)
    rows = parse_employees({
        "data": {"EX_BASE_05": {"Cur": [
            {
                "Afm": "123456789",
                "Eponimo": "Α",
                "Onoma": "Β",
                "DateProslipsis": "24/4/2026",
                "Amka": "15039012345",
                "AmIka": "1234567890",
            },
        ]}}
    })
    assert rows[0]["hire_date"] == date(2026, 4, 24)
    assert rows[0]["amka"] == "15039012345"
    assert rows[0]["amika"] == "1234567890"
    mixed = parse_employees({
        "data": {"EX_BASE_05": {"Cur": [
            {
                "afm": "123456789",
                "dateproslipsis": "01/06/2018",
                "AMKA": "150390-12345",
                "amika": "12 345",
            },
        ]}}
    })
    assert mixed[0]["hire_date"] == date(2018, 6, 1)
    assert mixed[0]["amka"] == "15039012345"
    assert mixed[0]["amika"] == "12345"
    from app.ergani_parse import parse_registry_digits

    assert parse_registry_digits({"amka": "15039012345"}, "Amka", "AMKA", max_len=11) == "15039012345"
