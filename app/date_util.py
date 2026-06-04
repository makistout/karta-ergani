"""Μορφές ημερομηνίας για Ergani API."""

from __future__ import annotations

from datetime import datetime, timedelta


def format_date_for_ergani(date_str: str | None) -> str:
    if not date_str:
        return datetime.today().strftime("%d/%m/%Y")
    s = str(date_str).strip()
    try:
        return datetime.strptime(s, "%Y-%m-%d").strftime("%d/%m/%Y")
    except ValueError:
        pass
    return s


def iso_to_ergani_dates(from_iso: str, to_iso: str, max_days: int = 31) -> list[str]:
    """Λίστα ημερομηνιών dd/mm/yyyy από ISO διάστημα (μέχρι max_days)."""
    try:
        start = datetime.strptime(from_iso.strip()[:10], "%Y-%m-%d")
        end = datetime.strptime(to_iso.strip()[:10], "%Y-%m-%d")
    except ValueError:
        return [format_date_for_ergani(from_iso)]
    if end < start:
        start, end = end, start
    out: list[str] = []
    d = start
    while d <= end and len(out) < max_days:
        out.append(d.strftime("%d/%m/%Y"))
        d += timedelta(days=1)
    return out


def format_f_date_time(f_date: str | None) -> str:
    """
    Ώρα κίνησης από f_date — ίδια λογική με ergani app/static/api-console.html
    (μέρος μετά το T ή κενό, πρώτα 8 χαρακτήρες = HH:MM:SS).
    """
    if not f_date:
        return ""
    time_val = str(f_date).strip()
    if "T" in time_val:
        time_val = time_val.split("T", 1)[1]
    elif " " in time_val:
        time_val = time_val.split(" ", 1)[1]
    return time_val[:8] if time_val else ""
