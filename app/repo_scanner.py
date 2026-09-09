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


def recent_punches(employer_afm, branch_aa, page, page_size=20):
    with cursor(commit=False) as cur:
        cur.execute("""
            SELECT w.id, w.employee_afm, w.work_date AS date,
                   CONCAT(emp.eponymo, N' ', emp.onoma) AS name,
                   p.event, p.hour AS time, p.protocol, p.next_day
            FROM dbo.karta_work_log w
            LEFT JOIN dbo.karta_employee emp ON emp.afm = w.employee_afm
            CROSS APPLY (VALUES
                ('in', w.hour_from, w.protocol_from, 0),
                ('out', w.hour_to, w.protocol_to,
                 CASE WHEN w.is_end_date_different = 1 THEN 1 ELSE 0 END)
            ) p(event, hour, protocol, next_day)
            WHERE w.employer_afm = ? AND w.branch_aa = ?
              AND NULLIF(LTRIM(RTRIM(p.hour)), '') IS NOT NULL
            ORDER BY DATEADD(day, p.next_day, TRY_CONVERT(date, w.work_date, 103)) DESC,
                     TRY_CONVERT(time, p.hour) DESC, w.id DESC, p.event DESC
            OFFSET ? ROWS FETCH NEXT ? ROWS ONLY
        """, (employer_afm, branch_aa, page * page_size, page_size + 1))
        rows = rows_to_dicts(cur)
    return rows[:page_size], len(rows) > page_size
