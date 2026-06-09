"""Parsing απαντήσεων Ergani (EX_BASE_02, EX_BASE_03)."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any


def extract_catalog_items(obj: Any) -> list[dict[str, str]]:
    if not obj or not isinstance(obj, dict):
        return []
    if isinstance(obj.get("ValueDescriptionPair"), list):
        return [
            {
                "value": str(p.get("Value", p.get("value", ""))),
                "description": str(p.get("Description", p.get("description", ""))),
            }
            for p in obj["ValueDescriptionPair"]
            if isinstance(p, dict)
        ]
    if isinstance(obj.get("Param"), list):
        out = []
        for p in obj["Param"]:
            if not isinstance(p, dict):
                continue
            val = p.get("Code", p.get("value", p.get("Value", "")))
            out.append({
                "value": str(val),
                "description": str(p.get("Description", p.get("description", ""))),
            })
        return out
    for key in obj:
        if isinstance(obj.get(key), dict):
            found = extract_catalog_items(obj[key])
            if found:
                return found
    return []


def unwrap_ergani_data(payload: Any) -> Any:
    if isinstance(payload, dict) and "data" in payload:
        return payload["data"]
    return payload


def parse_branches(payload: Any) -> list[dict[str, str]]:
    data = unwrap_ergani_data(payload)
    raw: list[Any] = []
    if isinstance(data, dict):
        for key in data:
            if isinstance(data[key], list):
                raw = data[key]
                break
            if isinstance(data[key], dict):
                for sub in data[key]:
                    if isinstance(data[key][sub], list):
                        raw = data[key][sub]
                        break
    items: list[dict[str, str]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        aa = str(item.get("Aa") or item.get("aa") or "0")
        desc = str(item.get("Perigrafi") or item.get("perigrafi") or "Παράρτημα")
        items.append({"aa": aa, "description": desc})
    if not items:
        items.append({"aa": "0", "description": "Κεντρικό (προεπιλογή)"})
    return items


def extract_raw_list(payload: Any) -> list[dict[str, Any]]:
    """Εξαγωγή λίστας dict από απάντηση ExecuteService."""
    data = unwrap_ergani_data(payload)
    raw: list[Any] = []
    if isinstance(data, dict):
        for val in data.values():
            if isinstance(val, list):
                raw = val
                break
            if isinstance(val, dict):
                for sub_v in val.values():
                    if isinstance(sub_v, list):
                        raw = sub_v
                        break
                    elif isinstance(sub_v, dict):
                        raw = [sub_v]
                        break
                if raw:
                    break
    elif isinstance(data, list):
        raw = data
    return [x for x in raw if isinstance(x, dict)]


def parse_work_log(payload: Any) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for item in extract_raw_list(payload):
        afm = str(item.get("Afm") or item.get("afm") or "").strip()
        diff = item.get("IsEndDateDifferentThanDate") or item.get("is_end_date_different_than_date")
        out.append({
            "employee_afm": afm[:9] if afm else "",
            "work_date": str(item.get("Date") or item.get("date") or ""),
            "hour_from": str(item.get("HourFrom") or item.get("hour_from") or ""),
            "hour_to": str(item.get("HourTo") or item.get("hour_to") or ""),
            "source_aa": str(item.get("Aa") or item.get("aa") or ""),
            "is_end_date_different": 1 if diff in (1, "1", True) else 0,
        })
    return out


_EMPLOYMENT_RE = re.compile(
    r"^(\S+)\s+(\d{1,2}:\d{2})\s*-\s*(\d{1,2}:\d{2})\s*$",
    re.I,
)


def _normalize_portal_date(value: str, fallback: str) -> str:
    s = (value or "").strip()
    for fmt in ("%d/%m/%Y", "%d/%m/%y"):
        try:
            return datetime.strptime(s, fmt).strftime("%d/%m/%Y")
        except ValueError:
            continue
    parts = s.split("/")
    if len(parts) == 3:
        try:
            d, m, y = int(parts[0]), int(parts[1]), int(parts[2])
            if y < 100:
                y += 2000
            return datetime(y, m, d).strftime("%d/%m/%Y")
        except ValueError:
            pass
    return fallback


def portal_rows_to_schedule_items(
    grid_rows: list[list[str]],
    *,
    default_work_date: str,
) -> list[dict[str, Any]]:
    """Μετατροπή γραμμών grid portal → karta_schedule."""
    out: list[dict[str, Any]] = []
    for cells in grid_rows:
        if len(cells) < 9:
            continue
        employment = (cells[8] or "").strip()
        hour_from, hour_to, shift = "", "", employment
        m = _EMPLOYMENT_RE.match(employment)
        if m:
            shift = m.group(1).upper()
            hour_from, hour_to = m.group(2), m.group(3)
        elif "ΑΝΑΠΑΥΣΗ" in employment.upper() or "ΡΕΠΟ" in employment.upper():
            shift = "ΑΝΑΠΑΥΣΗ/ΡΕΠΟ"
        elif "ΜΗ ΕΡΓΑΣΙΑ" in employment.upper():
            shift = "ΜΗ ΕΡΓΑΣΙΑ"

        break_txt = (cells[7] or "").strip()
        break_in_work = 1 if "Εντός" in break_txt else 0
        wd = _normalize_portal_date(cells[4], default_work_date)
        afm = str(cells[1]).strip()[:9]
        onoma = (cells[2] or "").strip()[:200]
        eponymo = (cells[3] or "").strip()[:200]
        extra_parts = [
            f"ΨΟ:{cells[5]}" if len(cells) > 5 else "",
            f"Κάρτα:{cells[6]}" if len(cells) > 6 else "",
            break_txt,
        ]
        extra = " · ".join(p for p in extra_parts if p)[:500]

        out.append({
            "employee_afm": afm,
            "onoma": onoma,
            "eponymo": eponymo,
            "work_date": wd,
            "hour_from": hour_from,
            "hour_to": hour_to,
            "shift_type": shift[:64],
            "break_minutes": 0,
            "break_in_work": break_in_work,
            "extra": extra,
            "source_aa": str(cells[0]).strip()[:32],
        })
    return out


def _normalize_portal_hour(value: str) -> str:
    s = (value or "").strip().replace("\xa0", "")
    if not s or s.lower() in ("&nbsp;", "—", "-"):
        return ""
    return s[:16]


def portal_rows_to_work_log_items(
    grid_rows: list[list[str]],
    *,
    default_work_date: str,
) -> list[dict[str, Any]]:
    """Μετατροπή γραμμών grid portal → karta_work_log."""
    out: list[dict[str, Any]] = []
    for cells in grid_rows:
        if len(cells) < 7:
            continue
        afm = str(cells[1]).strip()[:9]
        eponymo = (cells[2] or "").strip()[:200]
        onoma = (cells[3] or "").strip()[:200]
        wd = _normalize_portal_date(cells[4], default_work_date)
        hour_from = _normalize_portal_hour(cells[5])
        hour_to = _normalize_portal_hour(cells[6])
        out.append({
            "employee_afm": afm,
            "onoma": onoma,
            "eponymo": eponymo,
            "work_date": wd,
            "hour_from": hour_from,
            "hour_to": hour_to,
            "source_aa": str(cells[0]).strip()[:32],
            "is_end_date_different": 0,
        })
    return out


def parse_schedule(payload: Any) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for item in extract_raw_list(payload):
        afm = str(item.get("Afm") or item.get("afm") or "").strip()
        out.append({
            "employee_afm": afm[:9] if afm else "",
            "work_date": str(item.get("Date") or item.get("date") or ""),
            "hour_from": str(item.get("HourFrom") or item.get("hour_from") or ""),
            "hour_to": str(item.get("HourTo") or item.get("hour_to") or ""),
            "shift_type": str(item.get("Type") or item.get("type") or ""),
            "break_minutes": item.get("BreakMinutes") or item.get("break_minutes") or 0,
            "break_in_work": item.get("BreakInWork") or item.get("break_in_work") or 0,
            "extra": str(item.get("Extra") or item.get("extra") or "")[:500],
            "source_aa": str(item.get("Aa") or item.get("aa") or ""),
        })
    return out


def parse_flex_arrival_minutes(item: dict[str, Any]) -> int | None:
    """Ευέλικτη προσέλευση (λεπτά) — πεδίο EueliktoWrario από EX_BASE_05."""
    raw = item.get("EueliktoWrario")
    if raw is None:
        raw = item.get("eueliktoWrario")
    if raw is None or str(raw).strip() == "":
        return None
    try:
        value = int(str(raw).strip())
    except (TypeError, ValueError):
        return None
    return max(0, min(value, 120))


def parse_employees(payload: Any) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for item in extract_raw_list(payload):
        afm = str(item.get("afm") or item.get("Afm") or "").strip()
        if not afm:
            continue
        out.append({
            "afm": afm[:9],
            "eponymo": str(
                item.get("Eponimo") or item.get("Eponymo") or item.get("eponymo") or ""
            )[:200],
            "onoma": str(item.get("Onoma") or item.get("onoma") or "")[:200],
            "flex_arrival_minutes": parse_flex_arrival_minutes(item),
        })
    return out


def parse_employer_profile(payload: Any) -> dict[str, str]:
    data = unwrap_ergani_data(payload)
    if not isinstance(data, dict):
        return {}
    for key in ("EX_BASE_01", "Ergodotis", "ergodotis"):
        block = data.get(key)
        if isinstance(block, dict):
            erg = block.get("Ergodotis") or block.get("ergodotis") or block
            if isinstance(erg, dict):
                return {
                    "afm": str(erg.get("Afm") or erg.get("afm") or "")[:9],
                    "eponimia": str(
                        erg.get("Eponimia")
                        or erg.get("eponimia")
                        or erg.get("Eponymo")
                        or ""
                    )[:500],
                }
    return {
        "afm": str(data.get("Afm") or data.get("afm") or "")[:9],
        "eponimia": str(data.get("Eponimia") or data.get("eponimia") or "")[:500],
    }


def parse_employer_afm(payload: Any) -> str | None:
    data = unwrap_ergani_data(payload)
    if not isinstance(data, dict):
        return None
    for key in ("EX_BASE_01", "Ergodotis", "ergodotis"):
        block = data.get(key)
        if isinstance(block, dict):
            erg = block.get("Ergodotis") or block.get("ergodotis") or block
            if isinstance(erg, dict):
                afm = erg.get("Afm") or erg.get("afm")
                if afm:
                    return str(afm).strip()[:9]
    for key in ("Afm", "afm", "AFM"):
        if data.get(key):
            return str(data[key]).strip()[:9]
    return None
