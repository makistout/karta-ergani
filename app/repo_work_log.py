"""Πραγματική απασχόληση (EX_BASE_07) — pyodbc."""

from __future__ import annotations

from typing import Any

import pyodbc

from app.db import cursor
from app.date_util import format_date_for_ergani, format_f_date_time
from app.repo_schedule import list_schedule_for_range, list_schedule_for_store
from app.row_util import rows_to_dicts
from app.work_card_payload import norm_afm, tz_athens
from app.repo_work_log_core import (
    _sql_employee_active_column,
    list_work_log_for_range,
    list_work_log_for_store,
    replace_work_log_for_day,
    work_log_table_missing_message,
)
from app.repo_work_log_schedule import (
    _format_schedule_slot,
    enrich_work_log_rows_with_schedule,
)





def _pick_schedule_slot(
    slots: list[dict[str, Any]], row: dict[str, Any]
) -> dict[str, Any] | None:
    if not slots:
        return None
    if len(slots) == 1:
        return slots[0]
    wf = (row.get("hour_from") or "").strip()
    wt = (row.get("hour_to") or "").strip()
    if wf:
        for s in slots:
            sf = (s.get("hour_from") or "").strip()
            st = (s.get("hour_to") or "").strip()
            if sf == wf and (not wt or not st or wt == st):
                return s
    elif wt:
        for s in slots:
            st = (s.get("hour_to") or "").strip()
            if st == wt:
                return s
    return slots[0]


def _attach_schedule_fields(row: dict[str, Any], slots: list[dict[str, Any]]) -> None:
    if not slots:
        row["schedule_label"] = "—"
        row["schedule"] = None
        row["schedule_slots"] = []
        return
    row["schedule_slots"] = [
        {
            "hour_from": s.get("hour_from"),
            "hour_to": s.get("hour_to"),
            "shift_type": s.get("shift_type"),
        }
        for s in slots
    ]
    row["schedule_label"] = " · ".join(_format_schedule_slot(s) for s in slots)
    pick = _pick_schedule_slot(slots, row)
    row["schedule"] = (
        {
            "hour_from": pick.get("hour_from"),
            "hour_to": pick.get("hour_to"),
            "shift_type": pick.get("shift_type"),
        }
        if pick
        else None
    )


def _attach_card_punch_hint(
    row: dict[str, Any],
    slots: list[dict[str, Any]],
    *,
    submitted_types: set[str] | None = None,
) -> None:
    """Σημειώνει έλλειψη χτυπήματος κάρτας με ώρα από ψηφιακό ωράριο."""
    submitted = submitted_types or set()
    hf = (row.get("hour_from") or "").strip()
    ht = (row.get("hour_to") or "").strip()
    if hf and ht:
        return
    pick = _pick_schedule_slot(slots, row)
    if not pick:
        return
    sched_from = (pick.get("hour_from") or "").strip()
    sched_to = (pick.get("hour_to") or "").strip()
    if not hf and sched_from and "0" not in submitted:
        row["needs_card_punch"] = True
        row["card_event"] = "check_in"
        row["retro_time"] = sched_from
        return
    if not ht and hf and "1" not in submitted:
        from app.today_notify_logic import expected_exit_from_schedule_and_entry

        retro = expected_exit_from_schedule_and_entry(
            hour_from=hf,
            schedule_hour_from=sched_from,
            schedule_hour_to=sched_to,
        ) or sched_to
        row["needs_card_punch"] = True
        row["card_event"] = "check_out"
        row["retro_time"] = retro
        return


def enrich_work_log_history_with_card_punch(
    rows: list[dict[str, Any]],
    employer_afm: str,
    branch_aa: str,
    employee_afm: str,
) -> list[dict[str, Any]]:
    """Ιστορικό πραγματικής: ένδειξη χτυπήματος κάρτας από ψηφιακό ωράριο."""
    if not rows:
        return rows
    dates = _unique_work_dates(rows)
    if not dates:
        return rows
    by_key = _schedule_slots_by_employee_date(employer_afm, branch_aa, dates)
    card_types = _card_types_by_employee_work_date(employer_afm, branch_aa, dates)
    e_afm = norm_afm(employee_afm)
    for row in rows:
        wd = (row.get("work_date") or "").strip()
        slots = by_key.get((e_afm, wd), [])
        submitted = card_types.get((e_afm, wd), set())
        _attach_schedule_fields(row, slots)
        _attach_card_punch_hint(row, slots, submitted_types=submitted)
    return rows


def _unique_work_dates(rows: list[dict[str, Any]]) -> list[str]:
    return list(
        dict.fromkeys(
            str(r.get("work_date") or "").strip()
            for r in rows
            if (r.get("work_date") or "").strip()
        )
    )


def _schedule_slots_by_employee_date(
    employer_afm: str,
    branch_aa: str,
    dates: list[str],
) -> dict[tuple[str, str], list[dict[str, Any]]]:
    if not dates:
        return {}
    if len(dates) <= 1:
        sched_rows = list_schedule_for_store(employer_afm, branch_aa, dates[0])
    else:
        sched_rows = list_schedule_for_range(employer_afm, branch_aa, dates)
    by_key: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for s in sched_rows:
        afm = (s.get("employee_afm") or "").strip()
        wd = (s.get("work_date") or "").strip()
        if afm and wd:
            by_key.setdefault((afm, wd), []).append(s)
    return by_key


def _card_db_details_by_employee_work_date(
    employer_afm: str,
    branch_aa: str,
    work_dates: list[str],
) -> dict[tuple[str, str], dict[str, Any]]:
    """Δηλώσεις κάρτας ανά (εργαζόμενος, ημέρα) από karta_card_event."""
    from app.repo_card import list_card_events_for_store_range
    from app.telegram_punch_service import ergani_date_to_iso

    iso_to_wd: dict[str, str] = {}
    isos: list[str] = []
    for wd in work_dates:
        wd_s = str(wd or "").strip()
        if not wd_s:
            continue
        iso = ergani_date_to_iso(wd_s)
        if not iso:
            continue
        isos.append(iso)
        iso_to_wd[iso] = wd_s
    if not isos:
        return {}
    cards = list_card_events_for_store_range(
        employer_afm, branch_aa, min(isos), max(isos), limit=5000
    )
    out: dict[tuple[str, str], dict[str, Any]] = {}
    for card in cards:
        ref_iso = str(card.get("f_reference_date") or "").strip()[:10]
        wd = iso_to_wd.get(ref_iso) or format_date_for_ergani(ref_iso)
        e_afm = norm_afm(card.get("f_afm") or "")
        ft = str(card.get("f_type") or "").strip()
        if not e_afm or not wd or ft not in ("0", "1"):
            continue
        slot = out.setdefault(
            (e_afm, wd),
            {"types": set(), "check_in": None, "check_out": None},
        )
        hm = _card_event_time_hm(card.get("f_date"))
        entry = {
            "time": hm,
            "protocol": str(card.get("protocol") or "").strip() or None,
            "recorded_at": _format_recorded_at(card.get("declaration_created_at")),
        }
        if ft == "1":
            slot["check_out"] = entry
        else:
            slot["check_in"] = entry
        slot["types"].add(ft)
    return out


def _card_types_by_employee_work_date(
    employer_afm: str,
    branch_aa: str,
    work_dates: list[str],
) -> dict[tuple[str, str], set[str]]:
    details = _card_db_details_by_employee_work_date(employer_afm, branch_aa, work_dates)
    return {k: set(v.get("types") or set()) for k, v in details.items()}


def _work_log_missing_gaps(row: dict[str, Any]) -> set[str]:
    hf = str(row.get("hour_from") or "").strip()
    ht = str(row.get("hour_to") or "").strip()
    gaps: set[str] = set()
    if not hf:
        gaps.add("0")
    if not ht:
        gaps.add("1")
    return gaps


def _employee_row_is_active(row: dict[str, Any]) -> bool:
    v = row.get("employee_active")
    return not (v is False or v == 0 or v == "0")


def _merge_card_db_detail(
    card_details: dict[tuple[str, str], dict[str, Any]],
    token_details: dict[tuple[str, str], dict[str, Any]],
    key: tuple[str, str],
) -> tuple[set[str], dict[str, Any] | None, dict[str, Any] | None]:
    """Κλείσιμο ελλιπούς μόνο από karta_card_event· token για ένδειξη retro-hit."""
    db = card_details.get(key) or {}
    tok = token_details.get(key) or {}
    types = set(db.get("types") or set())
    cin = db.get("check_in")
    cout = db.get("check_out")
    tok_in = tok.get("check_in")
    tok_out = tok.get("check_out")
    if cin and tok_in and tok_in.get("from_token"):
        cin = {**cin, "from_token": True}
    elif not cin and tok_in and tok_in.get("time"):
        cin = tok_in
    if cout and tok_out and tok_out.get("from_token"):
        cout = {**cout, "from_token": True}
    elif not cout and tok_out and tok_out.get("time"):
        cout = tok_out
    return types, cin, cout


def _split_missing_rows_by_db_closure(
    rows: list[dict[str, Any]],
    card_details: dict[tuple[str, str], dict[str, Any]],
    token_details: dict[tuple[str, str], dict[str, Any]] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Χωρίζει ελλιπή: εκκρεμή vs κλεισμένα από δηλώσεις κάρτας / ολοκληρωμένο retro-hit."""
    token_details = token_details or {}
    pending: list[dict[str, Any]] = []
    closed: list[dict[str, Any]] = []
    for row in rows:
        if not _employee_row_is_active(row):
            continue
        afm = norm_afm(row.get("employee_afm") or "")
        wd = str(row.get("work_date") or "").strip()
        gaps = _work_log_missing_gaps(row)
        if not gaps:
            continue
        key = (afm, wd)
        submitted, card_db_in, card_db_out = _merge_card_db_detail(
            card_details, token_details, key
        )
        if gaps <= submitted:
            closed.append(
                {
                    **row,
                    "resolved_in_db": True,
                    "card_db_in": card_db_in,
                    "card_db_out": card_db_out,
                }
            )
        else:
            pending.append(row)
    return pending, closed


def _sort_missing_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:

    def _sort_key(r: dict[str, Any]) -> tuple:
        wd = str(r.get("work_date") or "")
        try:
            parts = wd.split("/")
            if len(parts) == 3:
                dkey = (int(parts[2]), int(parts[1]), int(parts[0]))
            else:
                dkey = (0, 0, 0)
        except ValueError:
            dkey = (0, 0, 0)
        return (dkey, str(r.get("hour_from") or ""), int(r.get("id") or 0))

    rows.sort(key=_sort_key, reverse=True)
    return rows


def enrich_work_log_rows_with_card_punch(
    rows: list[dict[str, Any]],
    employer_afm: str,
    branch_aa: str,
) -> list[dict[str, Any]]:
    """Ένδειξη χτυπήματος κάρτας ανά γραμμή (πολλοί εργαζόμενοι)."""
    if not rows:
        return rows
    dates = _unique_work_dates(rows)
    if not dates:
        return rows
    by_key = _schedule_slots_by_employee_date(employer_afm, branch_aa, dates)
    card_types = _card_types_by_employee_work_date(employer_afm, branch_aa, dates)
    for row in rows:
        afm = norm_afm(row.get("employee_afm") or "")
        wd = (row.get("work_date") or "").strip()
        slots = by_key.get((afm, wd), [])
        submitted = card_types.get((afm, wd), set())
        _attach_card_punch_hint(row, slots, submitted_types=submitted)
    return rows


def _work_log_missing_where_sql() -> str:
    return """
        w.employer_afm = ? AND w.branch_aa = ?
        AND w.work_date <> ?
        AND (
            NULLIF(LTRIM(RTRIM(ISNULL(w.hour_from, ''))), '') IS NULL
            OR NULLIF(LTRIM(RTRIM(ISNULL(w.hour_to, ''))), '') IS NULL
        )
    """


def _format_recorded_at(value: Any) -> str | None:
    """Ώρα καταγραφής δήλωσης (dd/mm/yyyy HH:mm, Europe/Athens)."""
    if value is None:
        return None
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return None
        if len(s) >= 16 and s[4] == "-":
            try:
                from datetime import datetime

                dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
                if dt.tzinfo is not None:
                    dt = dt.astimezone(tz_athens())
                else:
                    dt = dt.replace(tzinfo=tz_athens())
                return dt.strftime("%d/%m/%Y %H:%M")
            except ValueError:
                pass
        return s[:16].replace("T", " ")
    if hasattr(value, "strftime"):
        dt = value
        if hasattr(dt, "tzinfo") and dt.tzinfo is None:
            dt = dt.replace(tzinfo=tz_athens())
        elif hasattr(dt, "astimezone"):
            dt = dt.astimezone(tz_athens())
        return dt.strftime("%d/%m/%Y %H:%M")
    return None


def _card_event_time_hm(f_date: Any) -> str:
    raw = format_f_date_time(str(f_date or ""))
    if len(raw) >= 5:
        return raw[:5]
    return raw


def _list_work_log_missing_from_db(
    employer_afm: str,
    branch_aa: str,
    exclude_work_date: str,
) -> list[dict[str, Any]]:
    afm = norm_afm(employer_afm)
    aa = str(branch_aa or "0").strip()[:32] or "0"
    excl = str(exclude_work_date or "").strip()
    where = _work_log_missing_where_sql()
    with cursor(commit=False) as cur:
        cur.execute(
            f"""
            SELECT
                w.id, w.employee_afm, w.hour_from, w.hour_to, w.work_date,
                w.source_aa, w.is_end_date_different,
                emp.eponymo, emp.onoma, emp.flex_arrival_minutes,
                CAST(w.synced_at AS datetime2) AS synced_at,
                {_sql_employee_active_column("w")}
            FROM dbo.karta_work_log w
            LEFT JOIN dbo.karta_employee emp ON emp.afm = w.employee_afm
            WHERE {where}
            ORDER BY
                TRY_CONVERT(date, w.work_date, 103) DESC,
                w.hour_from DESC,
                w.id DESC
            """,
            (afm, aa, excl),
        )
        return rows_to_dicts(cur)


def _missing_rows_from_card_events(
    employer_afm: str,
    branch_aa: str,
    exclude_work_date: str,
) -> list[dict[str, Any]]:
    """Ελλιπή όταν υπάρχει δήλωση κάρτας αλλά λείπει/άδεια η γραμμή πραγματικής."""
    from datetime import datetime, timedelta

    from app.repo_card import list_card_events_for_store_range
    from app.work_card_payload import tz_athens

    afm = norm_afm(employer_afm)
    aa = str(branch_aa or "0").strip()[:32] or "0"
    excl = str(exclude_work_date or "").strip()
    today = datetime.now(tz_athens()).date()
    start_iso = (today - timedelta(days=120)).isoformat()
    end_iso = today.isoformat()
    cards = list_card_events_for_store_range(
        afm, aa, start_iso, end_iso, limit=5000
    )
    by_key: dict[tuple[str, str], dict[str, Any]] = {}
    for card in cards:
        ref_iso = str(card.get("f_reference_date") or "").strip()[:10]
        if not ref_iso:
            continue
        wd = format_date_for_ergani(ref_iso)
        if wd == excl:
            continue
        e_afm = norm_afm(card.get("f_afm") or "")
        if not e_afm:
            continue
        key = (e_afm, wd)
        slot = by_key.setdefault(
            key,
            {
                "check_in": "",
                "check_out": "",
                "eponymo": card.get("f_eponymo"),
                "onoma": card.get("f_onoma"),
                "flex_arrival_minutes": card.get("flex_arrival_minutes"),
            },
        )
        hm = _card_event_time_hm(card.get("f_date"))
        if str(card.get("f_type") or "").strip() == "1":
            if hm:
                slot["check_out"] = hm
        else:
            if hm:
                slot["check_in"] = hm
        if card.get("f_eponymo"):
            slot["eponymo"] = card.get("f_eponymo")
        if card.get("f_onoma"):
            slot["onoma"] = card.get("onoma")
        if card.get("flex_arrival_minutes") is not None:
            slot["flex_arrival_minutes"] = card.get("flex_arrival_minutes")

    gaps: list[dict[str, Any]] = []
    for (e_afm, wd), slot in by_key.items():
        wl_rows = [
            r
            for r in list_work_log_for_store(afm, aa, wd, limit=20)
            if norm_afm(r.get("employee_afm") or "") == e_afm
        ]
        wl = wl_rows[0] if wl_rows else None
        hf = str(wl.get("hour_from") or "").strip() if wl else ""
        ht = str(wl.get("hour_to") or "").strip() if wl else ""
        if hf and ht:
            continue
        if wl and (not hf or not ht):
            continue
        gaps.append(
            {
                "id": None,
                "employee_afm": e_afm,
                "hour_from": hf or slot.get("check_in") or "",
                "hour_to": ht or slot.get("check_out") or "",
                "work_date": wd,
                "source_aa": "",
                "is_end_date_different": 0,
                "eponymo": slot.get("eponymo"),
                "onoma": slot.get("onoma"),
                "flex_arrival_minutes": slot.get("flex_arrival_minutes"),
                "synced_at": None,
                "employee_active": True,
                "from_card_event": True,
            }
        )
    return gaps


def _merge_missing_card_rows(
    work_log_rows: list[dict[str, Any]],
    card_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    by_key: dict[tuple[str, str], dict[str, Any]] = {}
    for row in work_log_rows:
        e_afm = norm_afm(row.get("employee_afm") or "")
        wd = str(row.get("work_date") or "").strip()
        if e_afm and wd:
            by_key[(e_afm, wd)] = row
    for row in card_rows:
        e_afm = norm_afm(row.get("employee_afm") or "")
        wd = str(row.get("work_date") or "").strip()
        if not e_afm or not wd:
            continue
        key = (e_afm, wd)
        if key not in by_key:
            by_key[key] = row
            continue
        existing = by_key[key]
        if not str(existing.get("hour_from") or "").strip() and row.get("hour_from"):
            existing["hour_from"] = row["hour_from"]
        if not str(existing.get("hour_to") or "").strip() and row.get("hour_to"):
            existing["hour_to"] = row["hour_to"]
    merged = list(by_key.values())
    return _sort_missing_rows(merged)


def list_work_log_missing_cards_paged(
    employer_afm: str,
    branch_aa: str,
    exclude_work_date: str,
    page: int = 1,
    page_size: int = 20,
    closed_page: int = 1,
    closed_page_size: int = 20,
    store_id: int | None = None,
) -> tuple[list[dict[str, Any]], int, list[dict[str, Any]], int]:
    """Ελλιπή χωρισμένα σε εκκρεμή (portal) και ολοκληρωμένα από δηλώσεις κάρτας στη βάση."""
    pg = max(1, int(page))
    size = max(1, min(int(page_size), 100))
    cpg = max(1, int(closed_page))
    csize = max(1, min(int(closed_page_size), 100))
    wl_rows = _list_work_log_missing_from_db(employer_afm, branch_aa, exclude_work_date)
    card_rows = _missing_rows_from_card_events(
        employer_afm, branch_aa, exclude_work_date
    )
    merged = _merge_missing_card_rows(wl_rows, card_rows)
    dates = _unique_work_dates(merged)
    card_details = _card_db_details_by_employee_work_date(
        employer_afm, branch_aa, dates
    )
    token_details: dict[tuple[str, str], dict[str, Any]] = {}
    if store_id:
        from app.repo_telegram_punch import list_completed_punch_tokens_by_employee_date

        token_details = list_completed_punch_tokens_by_employee_date(int(store_id), dates)
    pending, closed = _split_missing_rows_by_db_closure(
        merged, card_details, token_details
    )
    pending = _sort_missing_rows(pending)
    closed = _sort_missing_rows(closed)
    pending_total = len(pending)
    closed_total = len(closed)
    pending_offset = (pg - 1) * size
    closed_offset = (cpg - 1) * csize
    return (
        pending[pending_offset : pending_offset + size],
        pending_total,
        closed[closed_offset : closed_offset + csize],
        closed_total,
    )


def list_work_log_history_for_employee(
    employer_afm: str,
    branch_aa: str,
    employee_afm: str,
    limit: int = 2000,
) -> list[dict[str, Any]]:
    lim = max(1, min(int(limit), 5000))
    afm = norm_afm(employer_afm)
    aa = str(branch_aa or "0").strip()[:32] or "0"
    e_afm = norm_afm(employee_afm)
    if not e_afm:
        return []
    with cursor(commit=False) as cur:
        cur.execute(
            f"""
            SELECT TOP ({lim})
                w.id, w.employee_afm, w.hour_from, w.hour_to, w.work_date,
                w.source_aa, w.is_end_date_different,
                emp.eponymo, emp.onoma, emp.flex_arrival_minutes,
                CAST(w.synced_at AS datetime2) AS synced_at,
                {_sql_employee_active_column("w")}
            FROM dbo.karta_work_log w
            LEFT JOIN dbo.karta_employee emp ON emp.afm = w.employee_afm
            WHERE w.employer_afm = ? AND w.branch_aa = ? AND w.employee_afm = ?
            ORDER BY
                TRY_CONVERT(date, w.work_date, 103) DESC,
                w.hour_from DESC,
                w.id DESC
            """,
            (afm, aa, e_afm),
        )
        return rows_to_dicts(cur)
