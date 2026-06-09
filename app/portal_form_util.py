"""Βοηθητικά για φόρμες ASP.NET portal Ergani."""

from __future__ import annotations

import re


def discover_date_input_names(html: str) -> tuple[str | None, str | None]:
    """Εύρεση name attributes για DateFromEdit / DateToEdit από HTML."""
    from_name: str | None = None
    to_name: str | None = None
    for m in re.finditer(r'<input\b([^>]*)\/?>', html, re.I):
        attrs = m.group(1)
        nm = re.search(r'\bname="([^"]+)"', attrs, re.I)
        if not nm:
            continue
        name = nm.group(1)
        norm = name.lower().replace("_", "").replace("$", "")
        if "datefromedit" in norm:
            from_name = name
        elif "datetoedit" in norm:
            to_name = name
    return from_name, to_name


def set_portal_dates(
    data: dict[str, str],
    html: str,
    date_from: str,
    date_to: str,
    *,
    fallback_from: tuple[str, ...] = (),
    fallback_to: tuple[str, ...] = (),
) -> None:
    """Ορίζει Από/Έως — ανακαλύπτει τα πραγματικά name από τη φόρμα."""
    from_name, to_name = discover_date_input_names(html)
    if from_name:
        data[from_name] = date_from
    for key in fallback_from:
        data[key] = date_from
    if to_name:
        data[to_name] = date_to
    for key in fallback_to:
        data[key] = date_to
