"""Πραγματική απασχόληση (EX_BASE_07) — pyodbc."""

from __future__ import annotations

from typing import Any

import pyodbc

from app.db import cursor
from app.date_util import format_date_for_ergani, format_f_date_time
from app.repo_schedule import list_schedule_for_range, list_schedule_for_store
from app.row_util import rows_to_dicts
from app.work_card_payload import norm_afm


def _sql_employee_active_column(alias: str = "w") -> str:
    """1 αν ο εργαζόμενος έχει ενεργή απασχόληση στο ίδιο παράρτημα."""
    a = alias
    return f"""
        CAST(CASE WHEN EXISTS (
            SELECT 1 FROM dbo.karta_employment e
            INNER JOIN dbo.karta_employee emp ON emp.id = e.employee_id
            INNER JOIN dbo.karta_employer em ON em.id = e.employer_id
            LEFT JOIN dbo.karta_parartima p ON p.id = e.parartima_id
            WHERE emp.afm = {a}.employee_afm
              AND em.afm = {a}.employer_afm
              AND e.active = 1
              AND (p.code_aa = {a}.branch_aa OR p.code_aa IS NULL)
        ) THEN 1 ELSE 0 END AS bit) AS employee_active
    """


def work_log_table_missing_message(exc: BaseException) -> str | None:
    if isinstance(exc, pyodbc.Error):
        err = exc.args[0] if exc.args else ""
        if err == "42S02" or "karta_work_log" in str(exc):
            return (
                "Λείπει ο πίνακας karta_work_log στη βάση. "
                "Τρέξτε το sql/alter_add_karta_work_log.sql στο SSMS."
            )
    return None


def replace_work_log_for_day(
    employer_afm: str,
    branch_aa: str,
    work_date: str,
    rows: list[dict[str, Any]],
) -> int:
    afm = norm_afm(employer_afm)
    aa = str(branch_aa or "0").strip()[:32] or "0"
    wd = str(work_date).strip()
    with cursor() as cur:
        cur.execute(
            """
            DELETE FROM dbo.karta_work_log
            WHERE employer_afm = ? AND branch_aa = ? AND work_date = ?
            """,
            (afm, aa, wd),
        )
        n = 0
        for row in rows:
            e_afm = norm_afm(row.get("employee_afm") or "") if row.get("employee_afm") else None
            cur.execute(
                """
                INSERT INTO dbo.karta_work_log (
                    employer_afm, branch_aa, work_date, employee_afm,
                    hour_from, hour_to, source_aa, is_end_date_different
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    afm,
                    aa,
                    wd,
                    e_afm,
                    row.get("hour_from"),
                    row.get("hour_to"),
                    row.get("source_aa"),
                    row.get("is_end_date_different"),
                ),
            )
            n += 1
        return n


def list_work_log_for_store(
    employer_afm: str,
    branch_aa: str,
    work_date: str,
    limit: int = 5000,
) -> list[dict[str, Any]]:
    lim = max(1, min(int(limit), 10000))
    afm = norm_afm(employer_afm)
    aa = str(branch_aa or "0").strip()[:32] or "0"
    wd = str(work_date).strip()
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
            WHERE w.employer_afm = ? AND w.branch_aa = ? AND w.work_date = ?
            ORDER BY w.hour_from, emp.eponymo, w.employee_afm
            """,
            (afm, aa, wd),
        )
        return rows_to_dicts(cur)


def list_work_log_for_range(
    employer_afm: str,
    branch_aa: str,
    work_dates: list[str],
    limit: int = 10000,
) -> list[dict[str, Any]]:
    if not work_dates:
        return []
    lim = max(1, min(int(limit), 20000))
    afm = norm_afm(employer_afm)
    aa = str(branch_aa or "0").strip()[:32] or "0"
    dates = list(dict.fromkeys(str(d).strip() for d in work_dates if d))[:62]
    placeholders = ",".join("?" for _ in dates)
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
            WHERE w.employer_afm = ? AND w.branch_aa = ? AND w.work_date IN ({placeholders})
            ORDER BY w.work_date, w.hour_from, emp.eponymo
            """,
            (afm, aa, *dates),
        )
        return rows_to_dicts(cur)


def _format_schedule_slot(row: dict[str, Any]) -> str:
    hf = (row.get("hour_from") or "").strip()
    ht = (row.get("hour_to") or "").strip()
    st = (row.get("shift_type") or "").strip()
    if hf or ht:
        return f"{hf or '—'} – {ht or '—'}"
    return st or "—"


def enrich_work_log_rows_with_schedule(
    rows: list[dict[str, Any]],
    employer_afm: str,
    branch_aa: str,
    work_dates: list[str],
) -> list[dict[str, Any]]:
    """Συμπλήρωση κάθε γραμμής πραγματικής με το ψηφιακό ωράριο (ίδια ημέρα / ΑΦΜ)."""
    if not rows or not work_dates:
        return rows
    if len(work_dates) <= 1:
        sched_rows = list_schedule_for_store(employer_afm, branch_aa, work_dates[0])
    else:
        sched_rows = list_schedule_for_range(employer_afm, branch_aa, work_dates)

    by_key: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for s in sched_rows:
        afm = (s.get("employee_afm") or "").strip()
        wd = (s.get("work_date") or "").strip()
        if afm and wd:
            by_key.setdefault((afm, wd), []).append(s)

    for row in rows:
        afm = (row.get("employee_afm") or "").strip()
        wd = (row.get("work_date") or "").strip()
        slots = by_key.get((afm, wd), [])
        if not slots:
            row["schedule_label"] = "—"
            row["schedule"] = None
            continue
        row["schedule_label"] = " · ".join(_format_schedule_slot(s) for s in slots)
        pick = slots[0] if len(slots) == 1 else None
        if len(slots) > 1:
            wf = (row.get("hour_from") or "").strip()
            wt = (row.get("hour_to") or "").strip()
            for s in slots:
                sf = (s.get("hour_from") or "").strip()
                st = (s.get("hour_to") or "").strip()
                if wf and sf == wf and (not wt or not st or wt == st):
                    pick = s
                    break
        row["schedule"] = (
            {
                "hour_from": pick.get("hour_from"),
                "hour_to": pick.get("hour_to"),
                "shift_type": pick.get("shift_type"),
            }
            if pick
            else None
        )
    return rows


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
        return
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


def _attach_card_punch_hint(row: dict[str, Any], slots: list[dict[str, Any]]) -> None:
    """Σημειώνει έλλειψη χτυπήματος κάρτας με ώρα από ψηφιακό ωράριο."""
    hf = (row.get("hour_from") or "").strip()
    ht = (row.get("hour_to") or "").strip()
    if hf and ht:
        return
    pick = _pick_schedule_slot(slots, row)
    if not pick:
        return
    sched_from = (pick.get("hour_from") or "").strip()
    sched_to = (pick.get("hour_to") or "").strip()
    if hf and not ht and sched_to:
        row["needs_card_punch"] = True
        row["card_event"] = "check_out"
        row["retro_time"] = sched_to
    elif not hf and sched_from:
        row["needs_card_punch"] = True
        row["card_event"] = "check_in"
        row["retro_time"] = sched_from


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
    e_afm = norm_afm(employee_afm)
    for row in rows:
        wd = (row.get("work_date") or "").strip()
        slots = by_key.get((e_afm, wd), [])
        _attach_schedule_fields(row, slots)
        _attach_card_punch_hint(row, slots)
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
    for row in rows:
        afm = norm_afm(row.get("employee_afm") or "")
        wd = (row.get("work_date") or "").strip()
        slots = by_key.get((afm, wd), [])
        _attach_card_punch_hint(row, slots)
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

    merged.sort(key=_sort_key, reverse=True)
    return merged


def list_work_log_missing_cards_paged(
    employer_afm: str,
    branch_aa: str,
    exclude_work_date: str,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[dict[str, Any]], int]:
    """Πραγματική με έλλειψη εισόδου/εξόδου + κενές γραμμές πραγματικής με δήλωση κάρτας."""
    pg = max(1, int(page))
    size = max(1, min(int(page_size), 100))
    offset = (pg - 1) * size
    wl_rows = _list_work_log_missing_from_db(employer_afm, branch_aa, exclude_work_date)
    card_rows = _missing_rows_from_card_events(
        employer_afm, branch_aa, exclude_work_date
    )
    merged = _merge_missing_card_rows(wl_rows, card_rows)
    total = len(merged)
    page_rows = merged[offset : offset + size]
    return page_rows, total


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
