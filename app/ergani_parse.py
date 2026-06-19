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


def _branch_aa(item: dict[str, Any]) -> str:
    for key in ("Aa", "aa", "f_aa", "f_aa_pararthmatos", "AA"):
        val = item.get(key)
        if val is not None and str(val).strip() != "":
            return str(val).strip()
    return "0"


def _branch_description(item: dict[str, Any]) -> str:
    for key in (
        "Perigrafi",
        "perigrafi",
        "Diethynsi",
        "diethynsi",
        "Titlos",
        "DiakritikosTitlos",
        "Eponimia",
        "Address",
        "address",
        "Kad",
        "StatusDescription",
        "f_comments",
        "Comments",
    ):
        val = item.get(key)
        if val and str(val).strip():
            return str(val).strip()[:200]
    return "Παράρτημα"


def _extract_ex_base_02_branch_items(data: dict[str, Any]) -> list[dict[str, Any]]:
    block = data.get("EX_BASE_02") if "EX_BASE_02" in data else data
    if isinstance(block, list):
        return [x for x in block if isinstance(x, dict)]
    if not isinstance(block, dict):
        return []

    par = block.get("Pararthma") or block.get("pararthma")
    if isinstance(par, list):
        return [x for x in par if isinstance(x, dict)]
    if isinstance(par, dict):
        for val in par.values():
            if isinstance(val, list):
                return [x for x in val if isinstance(x, dict)]
        if _branch_aa(par) != "0" or any(k in par for k in ("Aa", "aa", "f_aa", "Diethynsi")):
            return [par]

    for val in block.values():
        if isinstance(val, list) and val and isinstance(val[0], dict):
            if any(k in val[0] for k in ("Aa", "aa", "f_aa", "Diethynsi", "Perigrafi")):
                return [x for x in val if isinstance(x, dict)]
    return []


def _pick_str(item: dict[str, Any], *keys: str) -> str:
    for key in keys:
        val = item.get(key)
        if val is not None and str(val).strip():
            return str(val).strip()
    return ""


def _branch_item(item: dict[str, Any]) -> dict[str, Any]:
    """Κανονικοποίηση εγγραφής παραρτήματος από EX_BASE_02."""
    return {
        "aa": _branch_aa(item),
        "description": _branch_description(item),
        "address": _pick_str(item, "Address", "Diethynsi", "address", "diethynsi"),
        "ypiresia_sepe": _pick_str(item, "YpiresiaSepe", "ypiresiaSepe"),
        "ypiresia_oaed": _pick_str(item, "YpiresiaOaed", "ypiresiaOaed"),
        "kad": _pick_str(item, "Kad", "kad"),
        "kallikratis": _pick_str(item, "Kallikratis", "kallikratis"),
        "status_description": _pick_str(item, "StatusDescription", "statusDescription"),
    }


def parse_branches(payload: Any) -> list[dict[str, Any]]:
    data = unwrap_ergani_data(payload)
    raw: list[dict[str, Any]] = []
    if isinstance(data, dict):
        raw = _extract_ex_base_02_branch_items(data)
        if not raw:
            raw = [
                x
                for x in extract_raw_list(data)
                if isinstance(x, dict) and any(k in x for k in ("Aa", "aa", "f_aa"))
            ]
    items = [_branch_item(item) for item in raw]
    if not items:
        items.append({
            "aa": "0",
            "description": "Κεντρικό (προεπιλογή)",
            "address": "",
            "ypiresia_sepe": "",
            "ypiresia_oaed": "",
            "kad": "",
            "kallikratis": "",
            "status_description": "",
        })
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


def parse_authorized_service_names(payload: Any) -> list[str]:
    """Ονόματα services από GET WebServices/ServicesList."""
    data = unwrap_ergani_data(payload)
    if not isinstance(data, list):
        return []
    out: list[str] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or item.get("Name") or item.get("serviceCode") or "").strip()
        if name:
            out.append(name)
    return out

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


def _portal_hm_minutes(value: str) -> int | None:
    m = re.match(r"^(\d{1,2}):(\d{2})", (value or "").strip().rstrip("*"))
    if not m:
        return None
    return int(m.group(1)) * 60 + int(m.group(2))


def filter_portal_items_for_branch(
    items: list[dict[str, Any]],
    branch_aa: str,
) -> list[dict[str, Any]]:
    """Κρατά μόνο γραμμές portal του συγκεκριμένου παραρτήματος (ΑΑ)."""
    aa = str(branch_aa or "0").strip() or "0"
    return [
        it
        for it in items
        if (str(it.get("source_aa") or "").strip() or "0") == aa
    ]


def portal_rows_to_work_log_items(
    grid_rows: list[list[str]],
    *,
    default_work_date: str,
    default_branch_aa: str = "",
) -> list[dict[str, Any]]:
    """Μετατροπή γραμμών grid portal → karta_work_log."""
    branch_aa = str(default_branch_aa or "").strip()
    out: list[dict[str, Any]] = []
    for cells in grid_rows:
        if len(cells) < 7:
            continue
        afm = str(cells[1]).strip()[:9]
        eponymo = (cells[2] or "").strip()[:200]
        onoma = (cells[3] or "").strip()[:200]
        wd = _normalize_portal_date(cells[4], default_work_date)
        hour_from = _normalize_portal_hour(cells[5])
        hour_to_raw = _normalize_portal_hour(cells[6])
        hour_to = hour_to_raw.rstrip("*").strip()
        is_end_diff = 0
        if hour_to_raw.endswith("*"):
            is_end_diff = 1
        elif hour_from and hour_to:
            hf_m = _portal_hm_minutes(hour_from)
            ht_m = _portal_hm_minutes(hour_to)
            if hf_m is not None and ht_m is not None and ht_m < hf_m:
                is_end_diff = 1
        source_aa = str(cells[0] or "").strip()[:32]
        if not source_aa and branch_aa:
            source_aa = branch_aa
        out.append({
            "employee_afm": afm,
            "onoma": onoma,
            "eponymo": eponymo,
            "work_date": wd,
            "hour_from": hour_from,
            "hour_to": hour_to,
            "source_aa": source_aa,
            "is_end_date_different": is_end_diff,
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


def parse_monthly_status(payload: Any) -> list[dict[str, Any]]:
    """EX_BASE_04 — MiniaiaKatastash rows."""
    out: list[dict[str, Any]] = []
    for item in extract_raw_list(payload):
        afm = str(item.get("f_afm") or item.get("Afm") or item.get("afm") or "").strip()
        if not afm:
            continue
        out.append({
            "ergodoti_id": str(item.get("f_ergodoti_id") or "").strip()[:32] or None,
            "branch_aa": str(item.get("f_pararthma_aa") or "0").strip()[:32] or "0",
            "report_year": str(item.get("f_year") or "").strip(),
            "report_month": str(item.get("f_month") or "").strip(),
            "employee_afm": afm[:9],
            "days_work": item.get("f_arithmos_hmerwn_ergasias"),
            "days_telework": item.get("f_arithmos_hmerwn_tilergasias"),
            "days_repo": item.get("f_arithmos_hmerwn_anapaushs_repo"),
            "days_no_work": item.get("f_arithmos_hmerwn_mh_ergasias"),
            "days_normal_leave": item.get("f_arithmos_hmerwn_kanonikh_adeia"),
            "overtime_minutes": item.get("f_lepta_yperorias"),
            "overtime_days": item.get("f_arithmos_hmerwn_yperorias"),
            "days_work_card": item.get("f_arithmos_hmerwn_karta_ergasias"),
            "days_leave_insurance": item.get("f_synolo_hmerwn_adeias_asfalish"),
            "days_sick_insurance": item.get("f_synolo_hmerwn_astheneias_asfalish"),
        })
    return out
