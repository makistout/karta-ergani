"""Tests for Working Time Organization PDF sync helpers."""

from app.portal_wto_organization_pdf_sync import (
    extract_wto_select_items_from_html,
    parse_wto_submit_datetime,
    submission_code_for_declaration_type,
)


def test_parse_wto_submit_datetime_greek_ampm():
    am = parse_wto_submit_datetime("3/8/2026 11:45:26 πμ")
    assert am is not None
    assert am.hour == 11
    assert am.minute == 45
    pm = parse_wto_submit_datetime("10/8/2026 4:28:10 μμ")
    assert pm is not None
    assert pm.hour == 16
    assert pm.day == 10


def test_submission_code_for_declaration_type():
    assert submission_code_for_declaration_type(
        "Οργάνωση Χρόνου Εργασίας - Σταθερό Εβδομαδιαίο"
    ) == "WTOWeek"
    assert submission_code_for_declaration_type(
        "Οργάνωση Χρόνου Εργασίας - Μεταβαλλόμενο/Τροποποιούμενο ανά Ημέρα"
    ) == "WTODaily"


def test_extract_wto_select_items_from_html():
    html = """
    <tr>
      <td><input type="button" value="Επισκόπηση"
        onclick="if (Select(0, &#39;82167871|8/9/2026 9:19:00 πμ&#39;) == false) return false;" /></td>
      <td>0</td>
      <td>Υποβληθείσα</td>
      <td>Οργάνωση Χρόνου Εργασίας - Μεταβαλλόμενο/Τροποποιούμενο ανά Ημέρα</td>
      <td>8/9/2026 9:19:00 πμ</td>
      <td>ΟΡ82167871</td>
      <td>Όχι</td>
    </tr>
    """
    items = extract_wto_select_items_from_html(html)
    assert len(items) == 1
    assert items[0]["portal_id"] == "82167871"
    assert items[0]["protocol"] == "ΟΡ82167871"
    assert "Τροποποι" in items[0]["declaration_type"]
