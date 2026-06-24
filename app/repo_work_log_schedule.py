"""Schedule enrichment helpers for work-log rows."""

from __future__ import annotations

from typing import Any

from app.repo_schedule import list_schedule_for_range, list_schedule_for_store


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
