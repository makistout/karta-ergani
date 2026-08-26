"""Rule-based fallback για today_info / κάρτα — μόνο μετά από αποτυχία LLM."""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Any, Callable, Optional
from zoneinfo import ZoneInfo

from app.assistant_card_intent import card_action_direction_from_text

ResolveAfmsFn = Callable[[str, list[dict[str, Any]], Optional[int]], list[str]]


def _fold(text: str) -> str:
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
    "χθεσ",
    "εχθεσ",
    "τελειων",
    "ξεκινα",
    "ληγ",
    "αρχιζ",
)

_ATHENS = ZoneInfo("Europe/Athens")
_CHECKIN_STATUSES = frozenset({"needs_checkin", "late_arrival"})
_CHECKOUT_STATUSES = frozenset({"at_work", "needs_checkout"})


def looks_like_today_info(text: str) -> bool:
    folded = _fold(text)
    if not folded:
        return False
    # Imperative card punch is not an info question.
    if looks_like_card_punch(text):
        return False
    return any(hint in folded for hint in _INFO_HINTS)


def looks_like_card_punch(text: str) -> bool:
    """Άνοιξε/κλείσε κάρτα, clock in/out, είσοδος/έξοδος."""
    direction = card_action_direction_from_text(text)
    if not direction:
        return False
    folded = _fold(text)
    return any(
        token in folded
        for token in ("καρτ", "card", "εισοδ", "εξοδ", "checkin", "checkout", "clockin", "clockout")
    ) or "check in" in folded or "check out" in folded or "clock in" in folded or "clock out" in folded


def _wants_yesterday(text: str) -> bool:
    folded = _fold(text)
    return "χθεσ" in folded or "εχθεσ" in folded or "yesterday" in folded


def _wants_all(text: str) -> bool:
    folded = _fold(text)
    return any(
        token in folded
        for token in ("ολεσ", "ολουσ", "οσουσ", "οσα", "ολα", "all")
    ) or "καρτεσ" in folded or "καρτες" in folded


def _wants_schedule(text: str) -> bool:
    folded = _fold(text)
    return any(token in folded for token in ("βασει ωραρι", "ωραριου", "κατα ωραριο", "schedule"))


def _extract_punch_time(text: str) -> tuple[str | None, str]:
    """Επιστρέφει (HH:MM ή None, suffix _now|_retro|_schedule)."""
    if _wants_schedule(text):
        return None, "_schedule"
    folded = _fold(text)
    # «πριν 10 λεπτά» ή «10 λεπτά πριν»
    minutes_ago = re.search(r"πριν\s+(\d+)\s+λεπτ", folded)
    if not minutes_ago:
        minutes_ago = re.search(r"(\d+)\s+λεπτ\w*\s+πριν", folded)
    if minutes_ago:
        delta = timedelta(minutes=int(minutes_ago.group(1)))
        when = datetime.now(_ATHENS) - delta
        return when.strftime("%H:%M"), "_retro"
    clock = re.search(
        r"(?:στισ|στησ|στις|at)?\s*(\d{1,2})[:\.](\d{2})\b",
        folded,
    )
    if clock:
        hour = int(clock.group(1))
        minute = int(clock.group(2))
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return f"{hour:02d}:{minute:02d}", "_retro"
    return None, "_now"


def _open_card_rows(employees: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for row in employees:
        status = str(row.get("status") or "").strip()
        has_in = bool(row.get("card_in"))
        has_out = bool(row.get("card_out"))
        if status in _CHECKOUT_STATUSES or (has_in and not has_out):
            out.append(row)
    return out


def _checkin_rows(employees: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        row
        for row in employees
        if str(row.get("status") or "").strip() in _CHECKIN_STATUSES
    ]


def _working_rows(employees: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        row
        for row in employees
        if str(row.get("status") or "").strip() in {"at_work", "needs_checkout", "late_arrival"}
        or (row.get("card_in") and not row.get("card_out"))
    ]


def _pick_store(
    stores: list[Any],
    *,
    store_id: int | None,
) -> dict[str, Any] | None:
    if store_id is not None:
        for row in stores:
            if isinstance(row, dict) and int(row.get("store_id") or 0) == int(store_id):
                return row
    if len(stores) == 1 and isinstance(stores[0], dict):
        return stores[0]
    return None


def _format_open_lines(rows: list[dict[str, Any]]) -> list[str]:
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
    return lines


def _display_date(iso: str | None) -> str:
    raw = str(iso or "").strip()[:10]
    if len(raw) == 10 and raw[4] == "-" and raw[7] == "-":
        return f"{raw[8:10]}/{raw[5:7]}/{raw[0:4]}"
    return raw or "—"


def _home_employees(
    today_home: dict[str, Any],
    *,
    store_id: int | None,
    yesterday: bool,
) -> tuple[list[dict[str, Any]], str | None]:
    if yesterday:
        yblock = today_home.get("yesterday") if isinstance(today_home.get("yesterday"), dict) else {}
        ydate = str(yblock.get("date") or today_home.get("yesterday_date") or "").strip()[:10] or None
        ystores = yblock.get("stores") if isinstance(yblock.get("stores"), list) else []
        target = _pick_store(ystores, store_id=store_id)
        if not isinstance(target, dict):
            return [], ydate
        rows = [e for e in (target.get("employees") or []) if isinstance(e, dict)]
        return rows, ydate
    stores = today_home.get("stores") or []
    target = _pick_store(stores if isinstance(stores, list) else [], store_id=store_id)
    if not isinstance(target, dict):
        return [], None
    rows = [e for e in (target.get("employees") or []) if isinstance(e, dict)]
    return rows, None


def _empty_parsed(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "intent": "unknown",
        "store_id": None,
        "employee_afms": [],
        "employee_references": [],
        "employee_afm": None,
        "employee_reference": None,
        "date": None,
        "time": None,
        "hour_from": None,
        "hour_to": None,
        "leave_type": None,
        "confidence": 0.75,
        "clarification_question": None,
        "ambiguous_employee_afms": [],
        "pending_intent": None,
    }
    base.update(overrides)
    return base


def _name_choice_question(rows: list[dict[str, Any]]) -> str:
    labels = []
    for row in rows:
        label = str(row.get("name") or row.get("afm") or "—").strip()
        if label:
            labels.append(label)
    if len(labels) == 2:
        return f"Εννοείτε του {labels[0]} ή του {labels[1]};"
    joined = ", ".join(labels[:-1]) + f" ή του {labels[-1]}" if len(labels) > 1 else (labels[0] if labels else "—")
    return f"Εννοείτε του {joined};"


def build_card_punch_command(
    *,
    text: str,
    store_id: int | None,
    today_home: dict[str, Any],
    employees: list[dict[str, Any]] | None = None,
    resolve_afms: ResolveAfmsFn | None = None,
    focus_afms: list[str] | None = None,
) -> dict[str, Any] | None:
    """Άνοιξε/κλείσε κάρτα από κανόνες. None → αφήνει LLM."""
    if store_id is None or not looks_like_card_punch(text):
        return None
    direction = card_action_direction_from_text(text)
    if not direction:
        return None

    time_value, suffix = _extract_punch_time(text)
    intent = f"card_{direction}{suffix}"
    want_yesterday = _wants_yesterday(text)
    # Έξοδος χθες (overnight) — είσοδος χθες δεν καλύπτεται εδώ.
    if want_yesterday and direction != "check_out":
        return None

    home_rows, ydate = _home_employees(
        today_home, store_id=store_id, yesterday=want_yesterday,
    )
    today_iso = datetime.now(_ATHENS).date().isoformat()
    work_date = ydate if want_yesterday else today_iso

    named_afms: list[str] = []
    if resolve_afms is not None and employees is not None:
        named_afms = [
            str(a).strip()
            for a in resolve_afms(text, employees, store_id)
            if str(a or "").strip()
        ]
    named_afms = list(dict.fromkeys(named_afms))

    focus = [str(a).strip() for a in (focus_afms or []) if str(a or "").strip()]
    wants_group = _wants_all(text) or (
        direction == "check_out"
        and any(t in _fold(text) for t in ("ανοιχτ", "ολεσ", "ολουσ", "οσουσ"))
    )

    if named_afms:
        # Ένα επώνυμο → πολλοί: διευκρίνιση χωρίς LLM.
        if len(named_afms) > 1 and not wants_group:
            amb_rows = [
                row for row in (employees or home_rows)
                if str(row.get("afm") or "").strip() in set(named_afms)
                and (row.get("store_id") is None or int(row.get("store_id") or 0) == int(store_id))
            ]
            # Deduplicate by afm preferring catalog names.
            by_afm: dict[str, dict[str, Any]] = {}
            for row in amb_rows:
                afm = str(row.get("afm") or "").strip()
                if afm and afm not in by_afm:
                    by_afm[afm] = row
            for afm in named_afms:
                if afm not in by_afm:
                    by_afm[afm] = {"afm": afm, "name": afm}
            amb_list = [by_afm[a] for a in named_afms if a in by_afm]
            return _empty_parsed(
                intent=intent,
                store_id=store_id,
                date=work_date,
                time=time_value,
                employee_afms=[],
                ambiguous_employee_afms=named_afms,
                pending_intent=intent,
                clarification_question=_name_choice_question(amb_list),
                confidence=0.8,
            )
        afms = named_afms
    elif focus and not wants_group:
        afms = focus
    elif wants_group or not named_afms:
        if direction == "check_out":
            eligible = _open_card_rows(home_rows)
        else:
            eligible = _checkin_rows(home_rows)
        afms = [str(r.get("afm") or "").strip() for r in eligible if str(r.get("afm") or "").strip()]
        afms = list(dict.fromkeys(afms))
        # Singular «άνοιξε κάρτα» χωρίς όνομα/focus και πολλοί υποψήφιοι → LLM.
        if not wants_group and not focus and len(afms) != 1:
            if not afms:
                return _empty_parsed(
                    intent="today_info",
                    store_id=store_id,
                    date=work_date,
                    confidence=0.7,
                    clarification_question=(
                        "Δεν βρέθηκε εργαζόμενος για άνοιγμα κάρτας αυτή τη στιγμή."
                        if direction == "check_in"
                        else "Δεν υπάρχουν ανοιχτές κάρτες για κλείσιμο αυτή τη στιγμή."
                    ),
                )
            return None
    else:
        return None

    if not afms:
        return _empty_parsed(
            intent="today_info",
            store_id=store_id,
            date=work_date,
            confidence=0.7,
            clarification_question=(
                "Δεν βρέθηκε εργαζόμενος για άνοιγμα κάρτας αυτή τη στιγμή."
                if direction == "check_in"
                else "Δεν υπάρχουν ανοιχτές κάρτες για κλείσιμο αυτή τη στιγμή."
            ),
        )

    return _empty_parsed(
        intent=intent,
        store_id=store_id,
        date=work_date,
        time=time_value,
        employee_afms=afms,
        confidence=0.85,
    )


def _normalize_hhmm(text: str) -> str | None:
    raw = str(text or "").strip().replace(",", ":").replace(".", ":")
    if re.fullmatch(r"\d:[0-5]\d", raw):
        raw = f"0{raw}"
    if re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", raw):
        return raw
    return None


def _clock_from_info_text(text: str) -> str | None:
    match = re.search(r"(\d{1,2})[:\.]([0-5]\d)", str(text or ""))
    if not match:
        return None
    return _normalize_hhmm(f"{match.group(1)}:{match.group(2)}")


def _employee_end_times(row: dict[str, Any]) -> list[str]:
    times: list[str] = []
    to = _normalize_hhmm(str(row.get("schedule_to") or ""))
    if to:
        times.append(to)
    for item in row.get("intervals") or []:
        if not isinstance(item, dict):
            continue
        end = _normalize_hhmm(str(item.get("to") or item.get("hour_to") or ""))
        if end:
            times.append(end)
    return list(dict.fromkeys(times))


def _employee_start_times(row: dict[str, Any]) -> list[str]:
    times: list[str] = []
    start = _normalize_hhmm(str(row.get("schedule_from") or ""))
    if start:
        times.append(start)
    for item in row.get("intervals") or []:
        if not isinstance(item, dict):
            continue
        begin = _normalize_hhmm(str(item.get("from") or item.get("hour_from") or ""))
        if begin:
            times.append(begin)
    return list(dict.fromkeys(times))


def _schedule_criteria_answer(
    *,
    text: str,
    store_name: str,
    employees: list[dict[str, Any]],
) -> str | None:
    """«ποιος τελειώνει/ξεκινά στις 19.40» από schedule_* στο today_home."""
    folded = _fold(text)
    hhmm = _clock_from_info_text(text)
    if not hhmm:
        return None
    want_end = any(token in folded for token in ("τελειων", "ληγ", "finish", "ends"))
    want_start = any(token in folded for token in ("ξεκινα", "αρχιζ", "starts", "begin"))
    if not want_end and not want_start:
        # «στις 19:40» με ποιος/ποιες χωρίς ρήμα → τέλος βάρδιας.
        if any(token in folded for token in ("ποιος", "ποιοι", "ποια", "ποιες")):
            want_end = True
        else:
            return None

    matched: list[dict[str, Any]] = []
    for row in employees:
        times = _employee_end_times(row) if want_end else _employee_start_times(row)
        if hhmm in times:
            matched.append(row)

    name = store_name or "κατάστημα"
    verb = "τελειώνουν" if want_end else "ξεκινούν"
    if not matched:
        return f"Στο {name} κανείς δεν {verb} στις {hhmm}."
    lines = []
    for row in matched:
        label = str(row.get("name") or row.get("afm") or "—").strip()
        if want_end:
            end = next(iter(_employee_end_times(row)), hhmm)
            start = next(iter(_employee_start_times(row)), "")
            bit = label
            if start and end:
                bit += f" ({start}–{end})"
            else:
                bit += f" · έως {end}"
        else:
            start = next(iter(_employee_start_times(row)), hhmm)
            bit = f"{label} · από {start}"
        lines.append(f"• {bit}")
    return f"Στο {name} {verb} στις {hhmm}:\n" + "\n".join(lines)


def build_today_info_answer(
    *,
    text: str,
    store_id: int | None,
    store_name: str,
    today_home: dict[str, Any],
) -> str | None:
    folded = _fold(text)
    want_yesterday = _wants_yesterday(text)
    want_open = "ανοιχτ" in folded
    want_working = any(h in folded for h in ("εργαζ", "δουλευ", "ακομα"))

    if want_yesterday:
        yblock = today_home.get("yesterday") if isinstance(today_home.get("yesterday"), dict) else {}
        ydate = str(yblock.get("date") or today_home.get("yesterday_date") or "").strip()[:10]
        ystores = yblock.get("stores") if isinstance(yblock.get("stores"), list) else []
        target = _pick_store(ystores, store_id=store_id)
        if not isinstance(target, dict):
            if store_name:
                return (
                    f"Δεν υπάρχουν διαθέσιμα δεδομένα ανοιχτών καρτών χθες "
                    f"({_display_date(ydate)}) για το κατάστημα {store_name}."
                )
            return f"Δεν υπάρχουν διαθέσιμα δεδομένα ανοιχτών καρτών χθες ({_display_date(ydate)})."
        name = str(target.get("name") or store_name or "κατάστημα").strip()
        employees = [e for e in (target.get("employees") or []) if isinstance(e, dict)]
        rows = _open_card_rows(employees)
        if not rows:
            return (
                f"Στο κατάστημα {name} στις {_display_date(ydate)} "
                f"δεν υπάρχουν ανοιχτές κάρτες."
            )
        return (
            f"Στο {name}, ανοιχτές κάρτες χθες ({_display_date(ydate)}):\n"
            + "\n".join(_format_open_lines(rows))
        )

    stores = today_home.get("stores") or []
    target = _pick_store(stores if isinstance(stores, list) else [], store_id=store_id)
    if not isinstance(target, dict):
        if store_name:
            return f"Δεν υπάρχουν διαθέσιμα δεδομένα για το κατάστημα {store_name} σήμερα."
        return "Δεν υπάρχουν διαθέσιμα δεδομένα Αρχικής για σήμερα."

    name = str(target.get("name") or store_name or "κατάστημα").strip()
    employees = [e for e in (target.get("employees") or []) if isinstance(e, dict)]

    schedule_answer = _schedule_criteria_answer(
        text=text, store_name=name, employees=employees,
    )
    if schedule_answer:
        return schedule_answer

    if want_open:
        rows = _open_card_rows(employees)
        if not rows:
            return f"Στο κατάστημα {name} δεν υπάρχουν ανοιχτές κάρτες αυτή τη στιγμή."
        return f"Στο {name}, ανοιχτές κάρτες:\n" + "\n".join(_format_open_lines(rows))

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
    employees: list[dict[str, Any]] | None = None,
    resolve_afms: ResolveAfmsFn | None = None,
    focus_afms: list[str] | None = None,
) -> dict[str, Any] | None:
    """Επιστρέφει parsed command ή None αν δεν καλύπτεται χωρίς LLM."""
    punch = build_card_punch_command(
        text=text,
        store_id=store_id,
        today_home=today_home,
        employees=employees,
        resolve_afms=resolve_afms,
        focus_afms=focus_afms,
    )
    if punch is not None:
        return punch

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
    info_date = None
    if _wants_yesterday(text):
        info_date = str(today_home.get("yesterday_date") or "").strip()[:10] or None
        if not info_date:
            yblock = today_home.get("yesterday") if isinstance(today_home.get("yesterday"), dict) else {}
            info_date = str(yblock.get("date") or "").strip()[:10] or None
    return _empty_parsed(
        intent="today_info",
        store_id=store_id,
        date=info_date,
        confidence=0.7,
        clarification_question=answer,
    )
