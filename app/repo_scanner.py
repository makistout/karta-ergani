"""Latest store punches, paged in SQL without a total-count query."""
from app.db import cursor
from app.row_util import rows_to_dicts
from datetime import datetime, timedelta
from app.work_card_payload import tz_athens


def store_menu_details(employer_afm, branch_aa):
    with cursor(commit=False) as cur:
        cur.execute("""
            SELECT e.eponimia, p.description
            FROM dbo.karta_employer e
            LEFT JOIN dbo.karta_parartima p ON p.employer_id=e.id AND p.code_aa=?
            WHERE e.afm=?
        """, (branch_aa, employer_afm))
        row = cur.fetchone()
        details = {"legal_name": row[0] if row else None, "branch_description": row[1] if row else None}
        cur.execute("""
            SELECT TOP (1) e.f_date
            FROM dbo.karta_card_event e
            JOIN dbo.karta_declaration d ON d.id=e.declaration_id
            WHERE e.f_afm_ergodoti=? AND e.f_aa=? AND d.success=1
            ORDER BY TRY_CONVERT(datetimeoffset, e.f_date) DESC, e.id DESC
        """, (employer_afm, branch_aa))
        submitted = cur.fetchone()
    candidates = []
    if submitted and submitted[0]:
        try:
            at = datetime.fromisoformat(str(submitted[0]).replace("Z", "+00:00"))
            candidates.append(at.replace(tzinfo=tz_athens()) if at.tzinfo is None else at.astimezone(tz_athens()))
        except ValueError:
            pass
    punches, _ = recent_punches(employer_afm, branch_aa, 0, page_size=1)
    if punches:
        punch = punches[0]
        at = datetime.strptime(str(punch["date"]), "%d/%m/%Y")
        clock = str(punch["time"]).split(":")
        at = at.replace(hour=int(clock[0]), minute=int(clock[1]), second=int(float(clock[2])) if len(clock)>2 else 0, tzinfo=tz_athens())
        candidates.append(at + timedelta(days=1 if punch["next_day"] else 0))
    details["last_card_at"] = max(candidates).strftime("%d/%m/%Y %H:%M") if candidates else None
    return details


def _dedupe_recent_punches(rows: list[dict]) -> list[dict]:
    """Prefer card-event rows (src=card) when the same punch also exists in work_log."""
    best: dict[tuple, dict] = {}
    order: list[tuple] = []
    for row in rows:
        key = (
            str(row.get("employee_afm") or "").strip(),
            str(row.get("date") or "").strip(),
            str(row.get("event") or "").strip(),
            str(row.get("time") or "").strip()[:5],
        )
        if key not in best:
            best[key] = row
            order.append(key)
            continue
        prev = best[key]
        prev_score = (1 if prev.get("protocol") else 0) + (1 if prev.get("src") == "card" else 0)
        new_score = (1 if row.get("protocol") else 0) + (1 if row.get("src") == "card" else 0)
        if new_score > prev_score:
            best[key] = row
    return [best[key] for key in order]


def recent_punches(employer_afm, branch_aa, page, page_size=20):
    """Latest punches from work_log **and** successful card declarations.

    Scanner Αποστολές must show submissions even before portal sync fills
    karta_work_log (e.g. open card still only in karta_card_event).
    """
    page = max(0, int(page or 0))
    page_size = max(1, min(int(page_size or 20), 20))
    # Fetch a buffer so UNION+dedupe still fills the requested page.
    fetch_n = min((page + 1) * page_size * 3 + 1, 500)
    sql = f"""
        SELECT TOP ({fetch_n}) *
        FROM (
            SELECT
                w.id AS src_id,
                N'work' AS src,
                w.employee_afm,
                w.work_date AS date,
                CONCAT(emp.eponymo, N' ', emp.onoma) AS name,
                p.event,
                p.hour AS time,
                p.protocol,
                p.next_day,
                DATEADD(day, p.next_day, TRY_CONVERT(date, w.work_date, 103)) AS sort_date,
                TRY_CONVERT(time, p.hour) AS sort_time
            FROM dbo.karta_work_log w
            LEFT JOIN dbo.karta_employee emp ON emp.afm = w.employee_afm
            CROSS APPLY (VALUES
                ('in', w.hour_from, w.protocol_from, 0),
                ('out', w.hour_to, w.protocol_to,
                 CASE WHEN w.is_end_date_different = 1 THEN 1 ELSE 0 END)
            ) p(event, hour, protocol, next_day)
            WHERE w.employer_afm = ? AND w.branch_aa = ?
              AND NULLIF(LTRIM(RTRIM(p.hour)), '') IS NOT NULL

            UNION ALL

            SELECT
                e.id AS src_id,
                N'card' AS src,
                e.f_afm AS employee_afm,
                CASE
                    WHEN TRY_CONVERT(date, e.f_reference_date, 23) IS NOT NULL
                        THEN CONVERT(varchar(10), TRY_CONVERT(date, e.f_reference_date, 23), 103)
                    ELSE CONVERT(varchar(10), CAST(SWITCHOFFSET(TRY_CONVERT(datetimeoffset, e.f_date), '+03:00') AS date), 103)
                END AS date,
                LTRIM(RTRIM(CONCAT(ISNULL(e.f_eponymo, N''), N' ', ISNULL(e.f_onoma, N'')))) AS name,
                CASE WHEN LTRIM(RTRIM(e.f_type)) = N'1' THEN N'out' ELSE N'in' END AS event,
                CONVERT(varchar(5), CAST(SWITCHOFFSET(TRY_CONVERT(datetimeoffset, e.f_date), '+03:00') AS time), 108) AS time,
                d.protocol,
                0 AS next_day,
                COALESCE(
                    TRY_CONVERT(date, e.f_reference_date, 23),
                    CAST(SWITCHOFFSET(TRY_CONVERT(datetimeoffset, e.f_date), '+03:00') AS date)
                ) AS sort_date,
                CAST(SWITCHOFFSET(TRY_CONVERT(datetimeoffset, e.f_date), '+03:00') AS time) AS sort_time
            FROM dbo.karta_card_event e
            INNER JOIN dbo.karta_declaration d ON d.id = e.declaration_id
            WHERE e.f_afm_ergodoti = ?
              AND e.f_aa = ?
              AND d.success = 1
              AND LTRIM(RTRIM(ISNULL(e.f_type, N''))) IN (N'0', N'1')
              AND TRY_CONVERT(datetimeoffset, e.f_date) IS NOT NULL
        ) u
        ORDER BY u.sort_date DESC, u.sort_time DESC, u.src_id DESC, u.event DESC
    """
    with cursor(commit=False) as cur:
        cur.execute(sql, (employer_afm, branch_aa, employer_afm, branch_aa))
        rows = rows_to_dicts(cur)

    deduped = _dedupe_recent_punches(rows)
    start = page * page_size
    page_rows = deduped[start:start + page_size]
    has_next = len(deduped) > start + page_size
    cleaned = []
    for row in page_rows:
        cleaned.append({
            "id": row.get("src_id"),
            "employee_afm": row.get("employee_afm"),
            "date": row.get("date"),
            "name": (row.get("name") or "").strip() or None,
            "event": row.get("event"),
            "time": row.get("time"),
            "protocol": row.get("protocol"),
            "next_day": bool(row.get("next_day")),
        })
    return cleaned, has_next
