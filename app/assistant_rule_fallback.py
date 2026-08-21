"""Rule-based fallback για απλές ερωτήσεις σήμερα — χωρίς κανένα LLM."""

from __future__ import annotations

from typing import Any


def _fold(text: str) -> str:
    import re
    import unicodedata

    normalized = unicodedata.normalize("NFD", str(text or ""))
    stripped = "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")
    return re.sub(r"\s+", " ", stripped.casefold()).replace("ς", "σ").strip()


_INFO_HINTS = (
    "ανοιχτ",
    "εργαζ",
    "δουλευ",
    "ποιοι",
    "ποιες",
    "ποιος",
    "ποια",
    "ακομα",
    "τωρα",
    "status",
    "καταστασ",
    "ωραριο",
    "βαρδια",
)


def looks_like_today_info(text: str) -> bool:
    folded = _fold(text)
    if not folded:
        return False
    return any(hint in folded for hint in _INFO_HINTS)


def _open_card_rows(employees: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for row in employees:
        status = str(row.get("status") or "").strip()
        has_in = bool(row.get("card_in"))
        has_out = bool(row.get("card_out"))
        if status in {"at_work", "needs_checkout"} or (has_in and not has_out):
            out.append(row)
    return out


def _working_rows(employees: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        row
        for row in employees
        if str(row.get("status") or "").strip() in {"at_work", "needs_checkout", "late_arrival"}
        or (row.get("card_in") and not row.get("card_out"))
    ]


def build_today_info_answer(
    *,
    text: str,
    store_id: int | None,
    store_name: str,
    today_home: dict[str, Any],
) -> str | None:
    stores = today_home.get("stores") or []
    target = None
    if store_id is not None:
        for row in stores:
            if int(row.get("store_id") or 0) == int(store_id):
                target = row
                break
    elif len(stores) == 1:
        target = stores[0]
    if not isinstance(target, dict):
        if store_name:
            return f"Δεν υπάρχουν διαθέσιμα δεδομένα για το κατάστημα {store_name} σήμερα."
        return "Δεν υπάρχουν διαθέσιμα δεδομένα Αρχικής για σήμερα."

    name = str(target.get("name") or store_name or "κατάστημα").strip()
    employees = [e for e in (target.get("employees") or []) if isinstance(e, dict)]
    folded = _fold(text)

    want_open = "ανοιχτ" in folded
    want_working = any(h in folded for h in ("εργαζ", "δουλευ", "ακομα"))

    if want_open:
        rows = _open_card_rows(employees)
        if not rows:
            return f"Στο κατάστημα {name} δεν υπάρχουν ανοιχτές κάρτες αυτή τη στιγμή."
        lines = []
        for row in rows:
            label = str(row.get("name") or row.get("afm") or "—").strip()
            card_in = str(row.get("card_in") or "").strip()[:5]
            sched = ""
            if row.get("schedule_from") or row.get("schedule_to"):
                sched = f" ({row.get('schedule_from') or '—'}–{row.get('schedule_to') or '—'})"
            entry = f"{label}"
            if card_in:
                entry += f" · είσοδος {card_in}"
            entry += sched
            lines.append(f"• {entry}")
        return f"Στο {name}, ανοιχτές κάρτες:\n" + "\n".join(lines)

    if want_working or looks_like_today_info(text):
        rows = _working_rows(employees) if want_working else employees
        if want_working and not rows:
            return f"Στο κατάστημα {name} δεν φαίνεται να εργάζεται κανείς αυτή τη στιγμή."
        if not rows:
            return f"Στο κατάστημα {name} δεν υπάρχουν διαθέσιμα στοιχεία εργαζομένων για σήμερα."
        if want_working:
            lines = []
            for row in rows:
                label = str(row.get("name") or row.get("afm") or "—").strip()
                card_in = str(row.get("card_in") or "").strip()[:5]
                to = str(row.get("schedule_to") or "").strip()
                bit = label
                if card_in:
                    bit += f" · είσοδος {card_in}"
                if to:
                    bit += f" · έως {to}"
                lines.append(f"• {bit}")
            return f"Στο {name} εργάζονται ακόμα:\n" + "\n".join(lines)
        # Generic snapshot
        summary = target.get("summary") if isinstance(target.get("summary"), dict) else {}
        at_work = int(summary.get("at_work") or 0)
        completed = int(summary.get("completed") or 0)
        rest = int(summary.get("rest") or 0)
        return (
            f"Στο {name} σήμερα: σε εργασία {at_work}, ολοκληρωμένοι {completed}, "
            f"ρεπό/ανάπαυση {rest} (σύνολο {len(employees)})."
        )
    return None


def rule_based_parse(
    *,
    text: str,
    store_id: int | None,
    store_name: str,
    today_home: dict[str, Any],
) -> dict[str, Any] | None:
    """Επιστρέφει parsed command ή None αν δεν καλύπτεται χωρίς LLM."""
    if not looks_like_today_info(text):
        return None
    answer = build_today_info_answer(
        text=text,
        store_id=store_id,
        store_name=store_name,
        today_home=today_home,
    )
    if not answer:
        return None
    return {
        "intent": "today_info",
        "store_id": store_id,
        "employee_afms": [],
        "employee_references": [],
        "employee_afm": None,
        "employee_reference": None,
        "date": None,
        "time": None,
        "hour_from": None,
        "hour_to": None,
        "leave_type": None,
        "confidence": 0.7,
        "clarification_question": answer,
        "ambiguous_employee_afms": [],
    }
