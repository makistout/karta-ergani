"""Contract compliance alerts for the home card-report (today / tomorrow)."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Any

from app.apologistic import (
    _contract_kind,
    _contract_weekly_minutes,
    _day_state,
    _minutes,
    _working_slots,
)
from app.repo_employee_leave import load_current_year_normal_leave
from app.repo_employment_contract import list_current_for_store
from app.repo_schedule import list_schedule_for_range
from app.work_card_payload import norm_afm, tz_athens

CODE_SIXTH_DAY = "contract_sixth_day"
CODE_HOURS_OVER = "contract_hours_over"
CODE_LEAVE_OVER = "contract_leave_over"


def _annual_leave_entitlement(contract: dict[str, Any] | None) -> int | None:
    if not contract:
        return None
    days_raw = str(contract.get("weekly_work_days") or "")
    if "6" in days_raw:
        return 26
    if "5" in days_raw:
        return 22
    return None


def _parse_iso(value: str | None) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(text[:10] if fmt == "%Y-%m-%d" else text, fmt).date()
        except ValueError:
            continue
    return None


def _week_dates(focus: date) -> list[date]:
    monday = focus - timedelta(days=focus.weekday())
    return [monday + timedelta(days=i) for i in range(7)]


def _hm(total: int) -> str:
    total = max(0, int(total))
    return f"{total // 60}:{total % 60:02d}"


def _hours_label(total: int) -> str:
    """Ανθρώπινη διάρκεια (π.χ. «13 ώρες»), όχι ρολόι."""
    total = max(0, int(total))
    hours, minutes = divmod(total, 60)
    if minutes:
        return f"{hours}:{minutes:02d} ώρες"
    return f"{hours} ώρες"


def _parse_hours_field(raw: Any) -> int | None:
    if raw is None or str(raw).strip() == "":
        return None
    try:
        return max(0, int(round(float(str(raw).strip().replace(",", ".")) * 60)))
    except ValueError:
        return None


def _contract_week_cap(contract: dict[str, Any] | None) -> tuple[int | None, str]:
    """
    Όριο εβδομαδιαίων ωρών για alert στο κατάστημα.
    Προτεραιότητα: Συνολικές ώρες εβδομαδιαίως → Ώρες εβδομαδιαίως → 40ώ.
    """
    total = _parse_hours_field((contract or {}).get("total_weekly_hours"))
    if total is not None:
        return total, "Συνολικές ώρες εβδομαδιαίως"
    weekly = _parse_hours_field((contract or {}).get("weekly_hours"))
    if weekly is not None:
        return weekly, "Ώρες εβδομαδιαίως"
    fallback = _contract_weekly_minutes(contract)
    if fallback is not None:
        return fallback, "Ώρες εβδομαδιαίως"
    _, weekly_days = _contract_kind(contract)
    if weekly_days in (5, 6):
        return 40 * 60, "προεπιλογή πλήρους (40 ώρες)"
    return None, ""


def _ergani_date(value: Any) -> str:
    if hasattr(value, "strftime"):
        return value.strftime("%d/%m/%Y")
    text = str(value or "").strip()
    if not text:
        return ""
    parsed = _parse_iso(text)
    if parsed:
        return parsed.strftime("%d/%m/%Y")
    return text


def _slots_by_afm_date(schedule_rows: list[dict[str, Any]]) -> dict[tuple[str, str], list[dict[str, Any]]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in schedule_rows:
        afm = norm_afm(str(row.get("employee_afm") or ""))
        work_date = _ergani_date(row.get("work_date"))
        if not afm or not work_date:
            continue
        grouped[(afm, work_date)].append(row)
    return grouped


def _declared_work_minutes(slots: list[dict[str, Any]]) -> int:
    return sum(
        _minutes(slot.get("hour_from"), slot.get("hour_to")) or 0
        for slot in _working_slots(slots)
    )


def _is_declared_work_day(slots: list[dict[str, Any]]) -> bool:
    return _day_state(slots) == "Εργασία" and _declared_work_minutes(slots) > 0


def _is_leave_day(slots: list[dict[str, Any]], schedule_row: dict[str, Any] | None = None) -> bool:
    if slots and _day_state(slots) == "Άδεια":
        return True
    sched = schedule_row.get("schedule") if isinstance(schedule_row, dict) else None
    if isinstance(sched, dict):
        text = " ".join(
            str(sched.get(key) or "")
            for key in ("shift_type", "hour_from", "hour_to")
        ).upper()
        if "ΑΔΕΙΑ" in text:
            return True
    return False


def _alerts_for_employee_day(
    *,
    afm: str,
    focus: date,
    focus_ergani: str,
    contract: dict[str, Any] | None,
    week_slots: dict[tuple[str, str], list[dict[str, Any]]],
    leave_taken: int | None,
    row: dict[str, Any],
) -> list[dict[str, Any]]:
    alerts: list[dict[str, Any]] = []
    _, weekly_days = _contract_kind(contract)
    weekly_cap, cap_label = _contract_week_cap(contract)

    week = _week_dates(focus)
    work_days = 0
    week_minutes = 0
    focus_slots = week_slots.get((afm, focus_ergani), [])
    focus_is_work = _is_declared_work_day(focus_slots)
    for day in week:
        ergani = _ergani_date(day)
        slots = week_slots.get((afm, ergani), [])
        if _is_declared_work_day(slots):
            work_days += 1
            week_minutes += _declared_work_minutes(slots)

    if (
        focus_is_work
        and weekly_days == 5
        and work_days >= 6
    ):
        alerts.append({
            "code": CODE_SIXTH_DAY,
            "severity": "err",
            "label": (
                f"Παράβαση σύμβασης: {work_days}η εργάσιμη εβδομάδας "
                f"ενώ η σύμβαση είναι 5ήμερη"
            ),
        })

    if focus_is_work and weekly_cap is not None and week_minutes > weekly_cap:
        alerts.append({
            "code": CODE_HOURS_OVER,
            "severity": "err",
            "label": (
                f"Παράβαση σύμβασης: δηλωμένες {_hours_label(week_minutes)} αυτή την εβδομάδα "
                f"ενώ η σύμβαση προβλέπει {_hours_label(weekly_cap)}"
                + (f" ({cap_label})" if cap_label else "")
            ),
        })

    entitled = _annual_leave_entitlement(contract)
    if (
        _is_leave_day(focus_slots, row)
        and entitled is not None
        and leave_taken is not None
        and leave_taken >= entitled
    ):
        next_day_no = int(leave_taken) + (0 if leave_taken > entitled else 1)
        # Αν το archive ήδη μετράει ≥ δικαιούμενες, η σημερινή/αυριανή άδεια είναι υπέρβαση.
        shown = max(next_day_no, int(leave_taken))
        alerts.append({
            "code": CODE_LEAVE_OVER,
            "severity": "err",
            "label": (
                f"Παράβαση άδειας: {shown}η ημέρα κανονικής άδειας "
                f"ενώ δικαιούται {entitled}"
            ),
        })

    return alerts


def enrich_card_report_rows_with_contract_alerts(
    rows: list[dict[str, Any]],
    *,
    store_id: int,
    employer_afm: str,
    branch_aa: str,
) -> dict[str, int]:
    """Attach ``contract_alerts`` on each row and return summary counters."""
    summary = {
        CODE_SIXTH_DAY: 0,
        CODE_HOURS_OVER: 0,
        CODE_LEAVE_OVER: 0,
    }
    if not rows:
        return summary

    try:
        contracts = {
            norm_afm(str(c.get("employee_afm") or "")): c
            for c in list_current_for_store(employer_afm, branch_aa)
            if norm_afm(str(c.get("employee_afm") or ""))
        }
    except Exception:
        contracts = {}

    focus_by_row: list[date | None] = []
    weeks_needed: set[date] = set()
    afms: list[str] = []
    for row in rows:
        focus = _parse_iso(str(row.get("work_date") or ""))
        focus_by_row.append(focus)
        afm = norm_afm(str(row.get("employee_afm") or ""))
        if afm:
            afms.append(afm)
        if focus:
            weeks_needed.update(_week_dates(focus))

    ergani_dates = [_ergani_date(d) for d in sorted(weeks_needed)]
    try:
        schedule_rows = list_schedule_for_range(employer_afm, branch_aa, ergani_dates) if ergani_dates else []
    except Exception:
        schedule_rows = []
    week_slots = _slots_by_afm_date(schedule_rows)

    try:
        leave_map = load_current_year_normal_leave(
            store_id=int(store_id),
            employee_afms=afms,
            today=datetime.now(tz_athens()).date(),
        )
    except Exception:
        leave_map = {}

    for row, focus in zip(rows, focus_by_row):
        afm = norm_afm(str(row.get("employee_afm") or ""))
        if not afm or focus is None:
            row["contract_alerts"] = []
            continue
        leave = leave_map.get(afm)
        leave_taken = int(leave["days_taken"]) if leave and leave.get("days_taken") is not None else None
        alerts = _alerts_for_employee_day(
            afm=afm,
            focus=focus,
            focus_ergani=_ergani_date(focus),
            contract=contracts.get(afm),
            week_slots=week_slots,
            leave_taken=leave_taken,
            row=row,
        )
        row["contract_alerts"] = alerts
        for alert in alerts:
            code = str(alert.get("code") or "")
            if code in summary:
                summary[code] += 1
    return summary


def _schedule_import_contract_warnings(
    import_rows: list[dict[str, Any]],
    *,
    contracts: dict[str, dict[str, Any]],
    schedule_rows: list[dict[str, Any]],
    leave_map: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Return non-blocking contract warnings for a schedule Excel preview."""
    week_slots = _slots_by_afm_date(schedule_rows)
    affected: dict[str, set[date]] = defaultdict(set)
    names: dict[str, tuple[str, str]] = {}

    for row in import_rows:
        afm = norm_afm(str(row.get("employee_afm") or ""))
        focus = _parse_iso(str(row.get("work_date") or ""))
        action = str(row.get("import_action") or "").strip().lower()
        kind = str(row.get("change_kind") or "").strip().lower()
        if (
            not afm
            or focus is None
            or action not in ("work", "rest", "absent", "skip")
            or kind == "error"
            or bool(row.get("validation_errors"))
        ):
            continue

        ergani_date = _ergani_date(focus)
        if action != "skip":
            proposed = row.get("proposed_snapshot") or []
            replacement: list[dict[str, Any]] = []
            for slot in proposed if isinstance(proposed, list) else []:
                replacement.append({
                    "employee_afm": afm,
                    "work_date": ergani_date,
                    "hour_from": slot.get("hour_from"),
                    "hour_to": slot.get("hour_to"),
                    "shift_type": slot.get("shift_type") or slot.get("schedule_type"),
                    "schedule_type": slot.get("schedule_type") or slot.get("shift_type"),
                })
            week_slots[(afm, ergani_date)] = replacement
        affected[afm].add(focus)
        names[afm] = (
            str(row.get("eponymo") or "").strip(),
            str(row.get("onoma") or "").strip(),
        )

    warnings: list[dict[str, Any]] = []
    for afm, dates in affected.items():
        leave = leave_map.get(afm)
        leave_taken = int(leave["days_taken"]) if leave and leave.get("days_taken") is not None else None
        alerts_by_code: dict[str, dict[str, Any]] = {}
        for focus in sorted(dates):
            for alert in _alerts_for_employee_day(
                afm=afm,
                focus=focus,
                focus_ergani=_ergani_date(focus),
                contract=contracts.get(afm),
                week_slots=week_slots,
                leave_taken=leave_taken,
                row={},
            ):
                code = str(alert.get("code") or "")
                if code and code not in alerts_by_code:
                    alerts_by_code[code] = alert
        if alerts_by_code:
            eponymo, onoma = names.get(afm, ("", ""))
            warnings.append({
                "employee_afm": afm,
                "eponymo": eponymo,
                "onoma": onoma,
                "alerts": list(alerts_by_code.values()),
            })

    return sorted(
        warnings,
        key=lambda item: (
            str(item.get("eponymo") or "").casefold(),
            str(item.get("onoma") or "").casefold(),
            str(item.get("employee_afm") or ""),
        ),
    )


def build_schedule_import_contract_warnings(
    import_rows: list[dict[str, Any]],
    *,
    store_id: int,
    employer_afm: str,
    branch_aa: str,
) -> list[dict[str, Any]]:
    """Evaluate the uploaded schedule without changing or blocking its submission."""
    eligible = [
        row
        for row in import_rows
        if norm_afm(str(row.get("employee_afm") or ""))
        and _parse_iso(str(row.get("work_date") or "")) is not None
    ]
    if not eligible:
        return []

    try:
        contracts = {
            norm_afm(str(c.get("employee_afm") or "")): c
            for c in list_current_for_store(employer_afm, branch_aa)
            if norm_afm(str(c.get("employee_afm") or ""))
        }
    except Exception:
        contracts = {}

    weeks_needed: set[date] = set()
    afms: list[str] = []
    for row in eligible:
        focus = _parse_iso(str(row.get("work_date") or ""))
        if focus:
            weeks_needed.update(_week_dates(focus))
        afm = norm_afm(str(row.get("employee_afm") or ""))
        if afm:
            afms.append(afm)

    try:
        dates = [_ergani_date(day) for day in sorted(weeks_needed)]
        schedule_rows = list_schedule_for_range(employer_afm, branch_aa, dates) if dates else []
    except Exception:
        schedule_rows = []
    try:
        leave_map = load_current_year_normal_leave(
            store_id=int(store_id),
            employee_afms=afms,
            today=datetime.now(tz_athens()).date(),
        )
    except Exception:
        leave_map = {}

    return _schedule_import_contract_warnings(
        eligible,
        contracts=contracts,
        schedule_rows=schedule_rows,
        leave_map=leave_map,
    )
