"""Tests για ενημέρωση σύμβασης από Μητρώο πριν τη μισθοδοσία."""

from app.payroll import missing_wage_wait_message
from app.payroll_wage_enrich import (
    iter_payroll_wage_enrich_events,
    parse_enrich_employees,
)
from app.portal_employment_contract_sync import leftover_target_afms


def test_parse_enrich_employees_normalizes_and_dedupes():
    rows = parse_enrich_employees({
        "employees": [
            {"employee_afm": "185280545", "eponymo": "MOHAMMAD", "onoma": "AMIN"},
            {"afm": "185280545"},
            {"employee_afm": "abc"},
            {"employee_afm": "178756039", "name": "DJIBO DAOUDA"},
        ]
    })
    assert [row["employee_afm"] for row in rows] == ["185280545", "178756039"]
    assert rows[0]["name"] == "MOHAMMAD AMIN"
    assert rows[1]["name"] == "DJIBO DAOUDA"


def test_iter_payroll_wage_enrich_empty_is_done():
    events = list(iter_payroll_wage_enrich_events({"id": 1}, []))
    assert events[-1]["event"] == "done"
    assert events[-1]["success"] is True


def test_iter_payroll_wage_enrich_remaps_portal_done(monkeypatch):
    def fake_iter(ctx, *, run_id=None, only_afms=None, afm_labels=None):
        assert "185280545" in set(only_afms or [])
        assert afm_labels["185280545"] == "MOHAMMAD AMIN"
        yield {"event": "progress", "message": "x", "step": 1, "total": 1}
        yield {"event": "done", "result": {"success": True, "detail": "ok", "count": 1}}

    monkeypatch.setattr(
        "app.portal_employment_contract_sync.iter_employment_contract_sync_events",
        fake_iter,
    )
    events = list(
        iter_payroll_wage_enrich_events(
            {"id": 18},
            [{"employee_afm": "185280545", "eponymo": "MOHAMMAD", "onoma": "AMIN"}],
        )
    )
    assert events[0]["event"] == "progress"
    assert "Λείπουν στοιχεία" in events[0]["message"]
    assert "MOHAMMAD AMIN" in events[1]["message"]
    assert "Παρακαλώ περιμένετε" in events[1]["message"]
    done = events[-1]
    assert done["event"] == "done"
    assert done["success"] is True
    assert done["sync"]["detail"] == "ok"


def test_missing_wage_wait_message_is_sequential():
    text = missing_wage_wait_message("DJIBO DAOUDA", step=2, total=5)
    assert text.startswith("Δεν έχουμε στοιχεία για DJIBO DAOUDA.")
    assert "Μητρώο Εργάνη" in text
    assert "(2/5)" in text


def test_leftover_target_afms_preserves_label_order():
    leftover = leftover_target_afms(
        {"178756039", "185280545", "111111111"},
        {"111111111"},
        {"185280545": "MOHAMMAD AMIN", "178756039": "DJIBO"},
    )
    assert leftover == ["185280545", "178756039"]


def test_leftover_target_afms_empty_when_all_found():
    assert leftover_target_afms({"178756039"}, {"178756039"}) == []


def test_leftover_target_afms_ignores_blank_afm():
    from app.portal_employment_contract_sync import _norm_afm_or_empty

    assert _norm_afm_or_empty("") == ""
    assert leftover_target_afms({"", "178756039"}, set()) == ["178756039"]
