"""
Αρχειοθέτηση ψηφιακής οργάνωσης χρόνου εργασίας από portal Ergani.

Κατεβάζει το Excel από «Τρέχουσα Κατάσταση Ψηφιακής Οργάνωσης» και
αποθηκεύει parsed rows στον πίνακα karta_portal_schedule_archive.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta
from typing import Any

from app.db import cursor
from app.karta_log import KartaLogger
from app.portal_excel import _parse_excel_bytes, download_grid_excel
from app.portal_schedule_sync import (
    REQUEST_TIMEOUT,
    GRID_EVENT_TARGET,
    _extract_aspnet_form_data,
    _open_current_status,
    _pick_pararthma,
    _login_session,
    _portal_base,
)
from app.portal_form_util import set_portal_dates
from app.work_card_payload import norm_afm

_SCHEDULE_CTRL = (
    "ctl00$ctl00$ContentHolder$ContentHolder$ErgazomenosWorkingSearchControl"
)
_DATE_FROM_FALLBACK = (
    f"{_SCHEDULE_CTRL}$DateFromEdit",
    "ctl00_ctl00_ContentHolder_ContentHolder_ErgazomenosWorkingSearchControl_DateFromEdit",
)
_DATE_TO_FALLBACK = (
    f"{_SCHEDULE_CTRL}$DateToEdit",
    "ctl00_ctl00_ContentHolder_ContentHolder_ErgazomenosWorkingSearchControl_DateToEdit",
)

_RE_WORK = re.compile(
    r"ΕΡΓΑΣΙΑ\s+(\d{1,2}:\d{2})\s*-\s*(\d{1,2}:\d{2})"
)
_RE_OVERTIME = re.compile(
    r"Υπερωρία\s+(\d{1,2}:\d{2})\s*-\s*(\d{1,2}:\d{2})"
)
_RE_LEAVE = re.compile(
    r"(Κανονική άδεια|Άδεια\s+\S+)"
    r".*?Έτος\s+Αναφοράς:\s*(\d{4})"
    r".*?Αρ\.\s*Δικαιούμενων\s+ημερών:\s*(\d+)"
)


def parse_employment(raw: str) -> dict[str, Any]:
    """Parse στήλη «Απασχόληση» σε δομημένα πεδία."""
    text = (raw or "").strip()
    result: dict[str, Any] = {
        "employment_type": None,
        "work_from": None,
        "work_to": None,
        "overtime_from": None,
        "overtime_to": None,
        "leave_type": None,
        "leave_entitled_days": None,
        "leave_reference_year": None,
    }
    if not text:
        return result

    upper = text.upper()
    if upper.startswith("ΕΡΓΑΣΙΑ"):
        result["employment_type"] = "ΕΡΓΑΣΙΑ"
    elif "ΑΝΑΠΑΥΣΗ" in upper or "ΡΕΠΟ" in upper:
        result["employment_type"] = "ΑΝΑΠΑΥΣΗ"
    elif "ΜΗ ΕΡΓΑΣΙΑ" in upper:
        result["employment_type"] = "ΜΗ_ΕΡΓΑΣΙΑ"
    else:
        result["employment_type"] = text[:30]

    m = _RE_WORK.search(text)
    if m:
        result["work_from"] = m.group(1)
        result["work_to"] = m.group(2)

    m = _RE_OVERTIME.search(text)
    if m:
        result["overtime_from"] = m.group(1)
        result["overtime_to"] = m.group(2)

    m = _RE_LEAVE.search(text)
    if m:
        result["leave_type"] = m.group(1).strip()
        result["leave_reference_year"] = int(m.group(2))
        result["leave_entitled_days"] = int(m.group(3))

    return result


def _parse_date(value: str) -> date | None:
    for fmt in ("%d/%m/%Y", "%Y-%m-%d %H:%M:%S", "%m/%d/%Y"):
        try:
            return datetime.strptime(value.strip(), fmt).date()
        except (ValueError, TypeError):
            continue
    return None


def parse_archive_excel(content: bytes, content_type: str = "") -> list[dict[str, Any]]:
    """Parse Excel bytes → list of row dicts."""
    raw_rows = _parse_excel_bytes(content, content_type)
    if not raw_rows:
        return []
    headers = [h.strip() for h in raw_rows[0]]
    col = {h: i for i, h in enumerate(headers)}
    idx_aa = col.get("ΑΑ Παραρτηματος", col.get("ΑΑ Παραρτήματος", 0))
    idx_afm = col.get("ΑΦΜ", 1)
    idx_name = col.get("Όνομα", 2)
    idx_surname = col.get("Επώνυμο", 3)
    idx_date = col.get("Ημ/νια", col.get("Ημ/νία", 4))
    idx_digital = col.get("Ψηφιακή Οργάνωση", 5)
    idx_card = col.get("Κάρτα Εργασίας", 6)
    idx_break = col.get("Διάλειμμα", 7)
    idx_empl = col.get("Απασχόληση", 8)

    rows: list[dict[str, Any]] = []
    for cells in raw_rows[1:]:
        if len(cells) <= idx_afm:
            continue
        afm = norm_afm(cells[idx_afm])
        if not afm or not afm.isdigit():
            continue
        work_date = _parse_date(cells[idx_date] if len(cells) > idx_date else "")
        if not work_date:
            continue
        employment_raw = cells[idx_empl] if len(cells) > idx_empl else ""
        parsed = parse_employment(employment_raw)
        name_parts = []
        if len(cells) > idx_surname:
            name_parts.append(cells[idx_surname].strip())
        if len(cells) > idx_name:
            name_parts.append(cells[idx_name].strip())
        rows.append({
            "branch_aa": cells[idx_aa].strip() if len(cells) > idx_aa else "0",
            "employee_afm": afm,
            "employee_name": " ".join(name_parts) or None,
            "work_date": work_date,
            "has_digital_schedule": (cells[idx_digital].strip().upper() == "ΝΑΙ") if len(cells) > idx_digital else False,
            "has_work_card": (cells[idx_card].strip().upper() == "ΝΑΙ") if len(cells) > idx_card else False,
            "break_type": cells[idx_break].strip() if len(cells) > idx_break else None,
            "employment_raw": employment_raw or None,
            **parsed,
        })
    return rows


def upsert_archive_rows(
    store_id: int,
    employer_afm: str,
    reference_month: date,
    rows: list[dict[str, Any]],
) -> int:
    """MERGE rows στον πίνακα karta_portal_schedule_archive. Επιστρέφει count."""
    if not rows:
        return 0
    afm = norm_afm(employer_afm)
    count = 0
    with cursor(commit=True) as cur:
        for row in rows:
            cur.execute("""
                MERGE dbo.karta_portal_schedule_archive AS t
                USING (SELECT ? AS store_id, ? AS employee_afm, ? AS work_date) AS s
                ON t.store_id = s.store_id AND t.employee_afm = s.employee_afm AND t.work_date = s.work_date
                WHEN MATCHED THEN UPDATE SET
                    employer_afm=?, branch_aa=?, employee_name=?,
                    has_digital_schedule=?, has_work_card=?, break_type=?,
                    employment_raw=?, employment_type=?, work_from=?, work_to=?,
                    overtime_from=?, overtime_to=?,
                    leave_type=?, leave_entitled_days=?, leave_reference_year=?,
                    reference_month=?, synced_at=SYSDATETIMEOFFSET()
                WHEN NOT MATCHED THEN INSERT (
                    store_id, employer_afm, branch_aa, employee_afm, employee_name, work_date,
                    has_digital_schedule, has_work_card, break_type,
                    employment_raw, employment_type, work_from, work_to,
                    overtime_from, overtime_to,
                    leave_type, leave_entitled_days, leave_reference_year,
                    reference_month
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?);
            """, (
                store_id, row["employee_afm"], row["work_date"],
                # UPDATE params
                afm, row.get("branch_aa", "0"), row.get("employee_name"),
                row["has_digital_schedule"], row["has_work_card"], row.get("break_type"),
                row.get("employment_raw"), row.get("employment_type"),
                row.get("work_from"), row.get("work_to"),
                row.get("overtime_from"), row.get("overtime_to"),
                row.get("leave_type"), row.get("leave_entitled_days"), row.get("leave_reference_year"),
                reference_month,
                # INSERT params
                store_id, afm, row.get("branch_aa", "0"), row["employee_afm"], row.get("employee_name"), row["work_date"],
                row["has_digital_schedule"], row["has_work_card"], row.get("break_type"),
                row.get("employment_raw"), row.get("employment_type"),
                row.get("work_from"), row.get("work_to"),
                row.get("overtime_from"), row.get("overtime_to"),
                row.get("leave_type"), row.get("leave_entitled_days"), row.get("leave_reference_year"),
                reference_month,
            ))
            count += 1
    return count


def download_and_archive_month(
    store_cfg: dict[str, Any],
    reference_month: date,
    *,
    log: KartaLogger | None = None,
) -> dict[str, Any]:
    """
    Login στο portal, κατέβασε Excel για τον μήνα, parse + upsert.
    reference_month: 1η ημέρα μήνα αναφοράς (π.χ. 2026-07-01 για Ιούλιο).
    """
    store_id = int(store_cfg["id"])
    employer_afm = str(store_cfg["employer_afm"])
    branch_aa = str(store_cfg.get("branch_aa") or "0")

    month_from = reference_month.replace(day=1)
    next_month = (month_from + timedelta(days=32)).replace(day=1)
    month_to = next_month - timedelta(days=1)

    date_from = month_from.strftime("%d/%m/%Y")
    date_to = month_to.strftime("%d/%m/%Y")

    if log:
        log.info("schedule_archive.start", month=reference_month.isoformat(), date_from=date_from, date_to=date_to)

    session = _login_session(store_cfg)
    portal_base_url = _portal_base(store_cfg)
    html, url = _open_current_status(session, portal_base_url)

    data = _extract_aspnet_form_data(html, include_text=True)
    data[f"{_SCHEDULE_CTRL}$PararthmaSelection$PararthmaListEdit"] = _pick_pararthma(html, branch_aa)
    data[f"{_SCHEDULE_CTRL}$AfmEdit"] = ""
    data[f"{_SCHEDULE_CTRL}$EponimoBox"] = ""
    data[f"{_SCHEDULE_CTRL}$NameBox"] = ""
    set_portal_dates(data, html, date_from, date_to, fallback_from=_DATE_FROM_FALLBACK, fallback_to=_DATE_TO_FALLBACK)
    data[f"{_SCHEDULE_CTRL}$SearchControlSearchButton"] = "Αναζήτηση"

    import re as _re
    form_action = url
    m = _re.search(r'<form[^>]+action="([^"]*)"', html, _re.I)
    if m:
        from urllib.parse import urljoin
        form_action = urljoin(url, m.group(1))

    r = session.post(form_action, data=data, timeout=REQUEST_TIMEOUT, allow_redirects=True)
    if "error.aspx" in r.url.lower():
        raise RuntimeError(f"Portal error κατά αναζήτηση {date_from}–{date_to}")

    content, ctype = download_grid_excel(
        session, r.text, r.url,
        grid_event_target=GRID_EVENT_TARGET,
    )

    rows = parse_archive_excel(content, ctype)
    if log:
        log.info("schedule_archive.parsed", rows=len(rows))

    count = upsert_archive_rows(store_id, employer_afm, month_from, rows)

    if log:
        log.info("schedule_archive.done", upserted=count)

    return {"success": True, "rows_parsed": len(rows), "rows_upserted": count, "reference_month": month_from.isoformat()}


def run_monthly_archive(
    store_cfg: dict[str, Any],
    *,
    months_back: int = 2,
    log: KartaLogger | None = None,
) -> list[dict[str, Any]]:
    """Τρέχει archive για N μήνες πριν (default 2)."""
    today = date.today()
    results = []
    for i in range(months_back, 0, -1):
        ref = (today.replace(day=1) - timedelta(days=1))
        for _ in range(i - 1):
            ref = (ref.replace(day=1) - timedelta(days=1))
        ref = ref.replace(day=1)
        try:
            result = download_and_archive_month(store_cfg, ref, log=log)
            results.append(result)
        except Exception as ex:
            results.append({"success": False, "reference_month": ref.isoformat(), "error": str(ex)})
    return results


_MONTH_EL = (
    "",
    "Ιανουάριος",
    "Φεβρουάριος",
    "Μάρτιος",
    "Απρίλιος",
    "Μάιος",
    "Ιούνιος",
    "Ιούλιος",
    "Αύγουστος",
    "Σεπτέμβριος",
    "Οκτώβριος",
    "Νοέμβριος",
    "Δεκέμβριος",
)


def archive_months_for_new_store(today: date | None = None) -> list[date]:
    """
    Μήνες αρχείου για νέο κατάστημα: 1/1 τρέχοντος έτους έως και 2 μήνες πριν.

    Ιανουάριος/Φεβρουάριος → κενό (τίποτα να κατέβει ακόμη).
    Π.χ. Αύγουστος 2026 → Ιαν–Ιούν 2026.
    """
    base = today or date.today()
    if base.month <= 2:
        return []
    last_month = base.month - 2
    return [date(base.year, m, 1) for m in range(1, last_month + 1)]


def month_label_el(ref: date) -> str:
    name = _MONTH_EL[ref.month] if 1 <= ref.month <= 12 else str(ref.month)
    return f"{name} {ref.year}"


def iter_new_store_schedule_archive_events(
    store_cfg: dict[str, Any],
    *,
    run_id: str | None = None,
    today: date | None = None,
):
    """
    Progress events για αρχειοθέτηση ψηφιακής οργάνωσης κατά την είσοδο νέου καταστήματος.
    """
    log = KartaLogger(
        "new_store_schedule_archive",
        store_id=store_cfg.get("id"),
        store_name=store_cfg.get("name"),
        run_id=run_id,
        register_run=run_id is None,
    )
    months = archive_months_for_new_store(today)
    if not months:
        msg = (
            "Παράλειψη αρχείου ψηφιακής οργάνωσης "
            "(είσοδος Ιανουαρίου/Φεβρουαρίου — δεν υπάρχουν μήνες έως 2 πριν)."
        )
        log.info(msg)
        yield {"event": "progress", "message": msg, "step": 0, "total": 0}
        yield {
            "event": "done",
            "success": True,
            "message": msg,
            "sync": {"skipped": True, "reason": "jan_or_feb", "months": []},
        }
        return

    first = month_label_el(months[0])
    last = month_label_el(months[-1])
    total = len(months)
    start_msg = f"Αρχείο ψηφιακής οργάνωσης ({first} – {last}, {total} μήνες)…"
    log.info(start_msg, months=[m.isoformat() for m in months])
    yield {"event": "progress", "message": start_msg, "step": 0, "total": total}

    results: list[dict[str, Any]] = []
    upserted_total = 0
    for index, ref in enumerate(months, start=1):
        label = month_label_el(ref)
        progress_msg = f"Αρχείο ψηφιακής οργάνωσης: {label} ({index}/{total})…"
        log.info(progress_msg)
        yield {
            "event": "progress",
            "message": progress_msg,
            "step": index,
            "total": total,
        }
        try:
            result = download_and_archive_month(store_cfg, ref, log=log)
            results.append(result)
            upserted_total += int(result.get("rows_upserted") or 0)
        except Exception as ex:
            err = str(ex)
            log.error(f"Αποτυχία αρχείου {label}: {err}")
            yield {
                "event": "done",
                "success": False,
                "error": f"{label}: {err}",
                "message": f"Αποτυχία αρχείου ψηφιακής οργάνωσης ({label})",
                "sync": {
                    "months": [m.isoformat() for m in months],
                    "completed": results,
                    "failed_month": ref.isoformat(),
                    "rows_upserted": upserted_total,
                },
            }
            return

    done_msg = (
        f"Ολοκληρώθηκε αρχείο ψηφιακής οργάνωσης: {first} – {last} "
        f"({upserted_total} εγγραφές)."
    )
    log.info(done_msg, upserted=upserted_total)
    yield {
        "event": "done",
        "success": True,
        "message": done_msg,
        "sync": {
            "skipped": False,
            "months": [m.isoformat() for m in months],
            "results": results,
            "rows_upserted": upserted_total,
        },
    }
