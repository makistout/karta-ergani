"""Κοινή λογική νυχτερινών εξόδων πραγματικής (sync + προβολή UI)."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any


def ergani_date_sort_key(work_date: str) -> tuple[int, int, int]:
    try:
        dt = datetime.strptime(str(work_date).strip()[:10], "%d/%m/%Y")
        return (dt.year, dt.month, dt.day)
    except ValueError:
        return (9999, 12, 31)


def ergani_next_day(work_date: str) -> str:
    dt = datetime.strptime(str(work_date).strip()[:10], "%d/%m/%Y").date()
    return (dt + timedelta(days=1)).strftime("%d/%m/%Y")


def ergani_prev_day(work_date: str) -> str:
    dt = datetime.strptime(str(work_date).strip()[:10], "%d/%m/%Y").date()
    return (dt - timedelta(days=1)).strftime("%d/%m/%Y")


def is_next_calendar_day(prev_date: str, next_date: str) -> bool:
    try:
        prev = datetime.strptime(str(prev_date).strip()[:10], "%d/%m/%Y").date()
        nxt = datetime.strptime(str(next_date).strip()[:10], "%d/%m/%Y").date()
    except ValueError:
        return False
    return (nxt - prev).days == 1


def is_open_entry_item(item: dict[str, Any]) -> bool:
    hf = str(item.get("hour_from") or "").strip()
    ht = str(item.get("hour_to") or "").strip()
    return bool(hf) and not ht


def is_exit_only_item(item: dict[str, Any]) -> bool:
    hf = str(item.get("hour_from") or "").strip()
    ht = str(item.get("hour_to") or "").strip()
    return bool(ht) and not hf


def _exit_hour(item: dict[str, Any]) -> str:
    return str(item.get("hour_to") or "").strip().rstrip("*")


def _row_signature(row: dict[str, Any]) -> tuple[str, str, str, int]:
    return (
        str(row.get("employee_afm") or "").strip(),
        str(row.get("hour_from") or "").strip(),
        _exit_hour(row),
        int(bool(row.get("is_end_date_different"))),
    )


def find_overnight_orphan_exits(
    by_day: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    """Exit-only στη μέρα D που ανήκει ήδη (ή θα έπρεπε) στη D-1."""
    orphans: list[dict[str, Any]] = []
    sorted_days = sorted(by_day.keys(), key=ergani_date_sort_key)
    for idx in range(1, len(sorted_days)):
        prev_wd = sorted_days[idx - 1]
        next_wd = sorted_days[idx]
        if not is_next_calendar_day(prev_wd, next_wd):
            continue
        prev_items = by_day.get(prev_wd) or []
        for next_item in by_day.get(next_wd) or []:
            if not is_exit_only_item(next_item):
                continue
            afm = str(next_item.get("employee_afm") or "").strip()
            if not afm:
                continue
            next_ht = _exit_hour(next_item)
            for prev_item in prev_items:
                if str(prev_item.get("employee_afm") or "").strip() != afm:
                    continue
                if is_open_entry_item(prev_item):
                    orphans.append({
                        "work_date": next_wd,
                        "prev_work_date": prev_wd,
                        "employee_afm": afm,
                        "eponymo": next_item.get("eponymo"),
                        "hour_to": next_ht,
                        "reason": "open_entry_on_previous_day",
                    })
                    break
                prev_hf = str(prev_item.get("hour_from") or "").strip()
                prev_ht = _exit_hour(prev_item)
                if prev_hf and prev_ht and prev_ht == next_ht:
                    orphans.append({
                        "work_date": next_wd,
                        "prev_work_date": prev_wd,
                        "employee_afm": afm,
                        "eponymo": next_item.get("eponymo"),
                        "hour_to": next_ht,
                        "reason": "duplicate_exit_on_previous_day",
                    })
                    break
    return orphans


def repair_overnight_work_log_for_store(
    employer_afm: str,
    branch_aa: str,
    ergani_dates: list[str],
) -> dict[str, Any]:
    """Εφαρμογή merge σε συνεχόμενες μέρες και αποθήκευση αλλαγών στη βάση."""
    from app.repo_work_log_core import list_work_log_for_range, replace_work_log_for_day

    if not ergani_dates:
        return {"changed_days": [], "orphans_before": [], "orphans_after": []}

    dates_set = set(ergani_dates)
    for wd in ergani_dates:
        dates_set.add(ergani_prev_day(wd))
        dates_set.add(ergani_next_day(wd))
    all_dates = sorted(dates_set, key=ergani_date_sort_key)

    rows = list_work_log_for_range(employer_afm, branch_aa, all_dates)
    by_day: dict[str, list[dict[str, Any]]] = {wd: [] for wd in all_dates}
    for row in rows:
        wd = str(row.get("work_date") or "").strip()
        if wd in by_day:
            payload = {
                "employee_afm": row.get("employee_afm"),
                "hour_from": row.get("hour_from"),
                "hour_to": row.get("hour_to"),
                "source_aa": row.get("source_aa"),
                "is_end_date_different": row.get("is_end_date_different"),
                "eponymo": row.get("eponymo"),
                "onoma": row.get("onoma"),
            }
            by_day[wd].append(payload)

    orphans_before = find_overnight_orphan_exits(by_day)
    original_by_day = {
        wd: [dict(row) for row in (by_day.get(wd) or [])]
        for wd in all_dates
    }
    merged = merge_overnight_exits_across_days(by_day)
    orphans_after = find_overnight_orphan_exits(merged)

    changed_days: list[dict[str, Any]] = []
    for wd in all_dates:
        before_sig = sorted(_row_signature(r) for r in original_by_day.get(wd, []))
        after_sig = sorted(_row_signature(r) for r in merged.get(wd, []))
        if before_sig == after_sig:
            continue
        replace_work_log_for_day(employer_afm, branch_aa, wd, merged.get(wd, []))
        changed_days.append({
            "work_date": wd,
            "rows_before": len(original_by_day.get(wd, [])),
            "rows_after": len(merged.get(wd, [])),
        })

    return {
        "changed_days": changed_days,
        "orphans_before": orphans_before,
        "orphans_after": orphans_after,
    }


def merge_overnight_exits_across_days(
    by_day: dict[str, list[dict[str, Any]]],
) -> dict[str, list[dict[str, Any]]]:
    """
    Έξοδος μόνο στην επόμενη ημερομηνία (π.χ. 00:56 στη 10/07):
    - ενώνεται με ανοιχτή είσοδο της προηγούμενης (π.χ. 17:01 στη 09/07)
    - ή αφαιρείται αν η ίδια έξοδος υπάρχει ήδη στη προηγούμενη μέρα
    """
    sorted_days = sorted(by_day.keys(), key=ergani_date_sort_key)
    for idx in range(1, len(sorted_days)):
        prev_wd = sorted_days[idx - 1]
        next_wd = sorted_days[idx]
        if not is_next_calendar_day(prev_wd, next_wd):
            continue
        prev_items = by_day.setdefault(prev_wd, [])
        next_items = by_day.setdefault(next_wd, [])
        remove_indexes: set[int] = set()
        for ni, next_item in enumerate(next_items):
            if not is_exit_only_item(next_item):
                continue
            afm = str(next_item.get("employee_afm") or "").strip()
            if not afm:
                continue
            next_ht = _exit_hour(next_item)
            for prev_item in prev_items:
                if str(prev_item.get("employee_afm") or "").strip() != afm:
                    continue
                if is_open_entry_item(prev_item):
                    prev_item["hour_to"] = next_ht
                    prev_item["is_end_date_different"] = 1
                    remove_indexes.add(ni)
                    break
                prev_hf = str(prev_item.get("hour_from") or "").strip()
                prev_ht = _exit_hour(prev_item)
                if prev_hf and prev_ht and bool(prev_item.get("is_end_date_different")):
                    remove_indexes.add(ni)
                    break
                if prev_hf and prev_ht and prev_ht == next_ht:
                    remove_indexes.add(ni)
                    break
        if remove_indexes:
            by_day[next_wd] = [
                item for j, item in enumerate(next_items) if j not in remove_indexes
            ]
    return by_day
