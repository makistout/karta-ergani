"""Δημιουργία Excel template εβδομαδιαίου ωραρίου (ένα φύλλο «Εβδομάδα»)."""

from __future__ import annotations

import sys
from datetime import date

from app.schedule_excel_template import build_weekly_schedule_template_bytes, resolve_week_monday


def build(store_id: int, out_path: str, week_monday: date | None = None) -> None:
    monday = week_monday or resolve_week_monday("next")
    content, filename, meta = build_weekly_schedule_template_bytes(
        store_id=int(store_id),
        week_monday=monday,
    )
    with open(out_path, "wb") as fh:
        fh.write(content)
    print("OUT", out_path)
    print("FILE", filename)
    print("WEEK", monday.isoformat(), meta.get("week_to"))
    print("EMPLOYEES", meta.get("employee_count"))


if __name__ == "__main__":
    sid = int(sys.argv[1]) if len(sys.argv) > 1 else 6
    out = (
        sys.argv[2]
        if len(sys.argv) > 2
        else r"c:\inetpub\wwwroot\erganios\scripts\weekly_schedule_template_stanotas_mykonos.xlsx"
    )
    build(sid, out)
