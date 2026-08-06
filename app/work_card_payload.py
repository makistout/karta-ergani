"""Κατασκευή σώματος POST Documents/WRKCardSE."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import Any

from zoneinfo import ZoneInfo

SUBMISSION_CODE_WRK_CARD = "WRKCardSE"

# Λίστα Ergani — εκπρόθεσμη δήλωση κάρτας (εγχειρίδιο, παράρτημα)
AITIOLOGIA_CODES: dict[str, str] = {
    "001": "ΠΡΟΒΛΗΜΑ ΣΤΗΝ ΗΛΕΚΤΡΟΔΟΤΗΣΗ/ΤΗΛΕΠΙΚΟΙΝΩΝΙΕΣ",
    "002": "ΠΡΟΒΛΗΜΑ ΣΤΑ ΣΥΣΤΗΜΑΤΑ ΤΟΥ ΕΡΓΟΔΟΤΗ",
    "003": "ΠΡΟΒΛΗΜΑ ΣΥΝΔΕΣΗΣ ΜΕ ΤΟ ΠΣ ΕΡΓΑΝΗ",
}
RETRO_AITIOLOGIA_INTERNET = "001"


def ergani_forbids_aitiologia(parsed: Any) -> bool:
    """True αν η Ergani απαγορεύει δήλωση λόγου καθυστέρησης → retry χωρίς f_aitiologia."""
    import json

    try:
        text = json.dumps(parsed, ensure_ascii=False)
    except TypeError:
        text = str(parsed or "")
    return "δεν πρέπει να δηλώνεται λόγος καθυστέρησης" in text.lower()


class WorkCardPayloadError(ValueError):
    pass


@lru_cache(maxsize=1)
def tz_athens():
    try:
        return ZoneInfo("Europe/Athens")
    except ZoneInfoNotFoundError:
        return timezone(timedelta(hours=3), name="EEST-fallback")


def norm_afm(s: str | None) -> str:
    if not s:
        raise WorkCardPayloadError("Λείπει ΑΦΜ")
    x = str(s).strip().replace(" ", "")[:9]
    if len(x) != 9 or not x.isdigit():
        raise WorkCardPayloadError("Το ΑΦΜ πρέπει να έχει ακριβώς 9 ψηφία")
    return x


def f_type_from_event(event: str | None, explicit_f_type: str | None) -> str:
    if explicit_f_type is not None and str(explicit_f_type).strip() != "":
        return str(explicit_f_type).strip()[:16]
    e = (event or "").strip().lower()
    if e in ("check_in", "arrival", "start", "in", "εισοδος", "είσοδος"):
        return "0"
    if e in ("check_out", "departure", "end", "out", "εξοδος", "έξοδος"):
        return "1"
    raise WorkCardPayloadError(
        "Χρειάζεται event (check_in / check_out) ή ρητό f_type"
    )


def parse_event_at(raw: str | None, reference_date: str | None) -> datetime:
    now = datetime.now(tz_athens())
    if raw:
        s = str(raw).strip()
        try:
            dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=tz_athens())
            return dt.astimezone(tz_athens())
        except ValueError as ex:
            raise WorkCardPayloadError("Μη έγκυρο event_at (ISO 8601)") from ex
    if reference_date:
        rd = str(reference_date).strip()[:10]
        try:
            d = datetime.strptime(rd, "%Y-%m-%d").date()
        except ValueError as ex:
            raise WorkCardPayloadError("Μη έγκυρο reference_date") from ex
        return datetime.combine(d, now.time(), tzinfo=tz_athens())
    return now


def _flex_tolerance_minutes(flex_arrival_minutes: int | None, *, default: int = 15) -> int:
    from app.card_report import _flex_tolerance_minutes as _flex

    return _flex(flex_arrival_minutes, default=default)


def _hm_to_minutes(value: str | None) -> int | None:
    from app.card_report import _hm_to_minutes as _hm

    return _hm(value)


def wrk_card_needs_aitiologia(
    *,
    f_type: str,
    reference_date: str,
    event_at: str | None,
    schedule_hour_from: str | None = None,
    schedule_hour_to: str | None = None,
    flex_arrival_minutes: int | None = None,
) -> bool:
    """Αν χρειάζεται f_aitiologia: προηγούμενη ημέρα πάντα· σήμερα έλεγχος ώρας+ευελιξίας."""
    today_iso = datetime.now(tz_athens()).date().isoformat()
    ref = str(reference_date or "").strip()[:10]
    if not ref and event_at:
        ref = str(event_at).strip()[:10]
    if ref and ref != today_iso:
        return True
    if not event_at:
        return False

    dt = parse_event_at(event_at, ref or None)
    punch_min = dt.hour * 60 + dt.minute
    tol = _flex_tolerance_minutes(flex_arrival_minutes)
    ft = str(f_type).strip()

    if ft == "0":
        s_start = _hm_to_minutes(schedule_hour_from)
        # Αν δεν έχουμε ωράριο/ευελιξία, δεν μπορούμε να αποφανθούμε.
        # Αφήνουμε το retry/error-handling στους routes να χειριστεί XSD/Ergani μηνύματα.
        if s_start is None:
            return False
        return punch_min < s_start or punch_min > s_start + tol

    s_end = _hm_to_minutes(schedule_hour_to)
    if s_end is None:
        return False
    return punch_min < s_end - tol or punch_min > s_end + tol


def resolve_wrk_card_aitiologia(
    *,
    f_type: str,
    event_at: str | None,
    reference_date: str | None,
    requested_aitiologia: str | None,
    schedule_hour_from: str | None = None,
    schedule_hour_to: str | None = None,
    flex_arrival_minutes: int | None = None,
) -> str | None:
    """Απόφαση αιτιολογίας WRKCardSE πριν την υποβολή στην Ergani."""
    ref = str(reference_date or "").strip()[:10] or None
    if event_at and not ref:
        ref = str(event_at).strip()[:10]

    if not wrk_card_needs_aitiologia(
        f_type=f_type,
        reference_date=ref or "",
        event_at=event_at,
        schedule_hour_from=schedule_hour_from,
        schedule_hour_to=schedule_hour_to,
        flex_arrival_minutes=flex_arrival_minutes,
    ):
        return None

    if requested_aitiologia:
        ait = normalize_aitiologia(requested_aitiologia)
        return ait or RETRO_AITIOLOGIA_INTERNET
    return RETRO_AITIOLOGIA_INTERNET


def lookup_punch_schedule_context(
    *,
    employer_afm: str,
    branch_aa: str,
    employee_afm: str,
    work_date_ergani: str,
) -> dict[str, Any]:
    """Ψηφ. ωράριο + ευελιξία + πραγματική είσοδος για έλεγχο αιτιολογίας."""
    from app.repo_entities import flex_arrival_map_for_employer
    from app.repo_work_log import enrich_work_log_rows_with_schedule, list_work_log_for_store

    wd = str(work_date_ergani or "").strip()
    emp = norm_afm(employee_afm)
    row: dict[str, Any] = {
        "employee_afm": emp,
        "work_date": wd,
        "hour_from": None,
        "hour_to": None,
    }
    wl_rows = list_work_log_for_store(employer_afm, branch_aa, wd, limit=20)
    for wl in wl_rows:
        if norm_afm(str(wl.get("employee_afm") or "")) == emp:
            row["hour_from"] = wl.get("hour_from")
            row["hour_to"] = wl.get("hour_to")
            break
    enrich_work_log_rows_with_schedule([row], employer_afm, branch_aa, [wd])
    sched = row.get("schedule") if isinstance(row.get("schedule"), dict) else {}
    flex_map = flex_arrival_map_for_employer(employer_afm, branch_aa)
    return {
        "schedule_hour_from": str((sched or {}).get("hour_from") or "").strip() or None,
        "schedule_hour_to": str((sched or {}).get("hour_to") or "").strip() or None,
        "flex_arrival_minutes": flex_map.get(emp),
        "work_hour_from": str(row.get("hour_from") or "").strip() or None,
    }


def normalize_aitiologia(raw: str | None) -> str | None:
    """Μετατροπή σε κωδικό Ergani (001/002/003) — όχι ελεύθερο κείμενο."""
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    if s in AITIOLOGIA_CODES:
        return s
    upper = s.upper()
    if any(
        tok in upper
        for tok in (
            "INTERNET",
            "ΙΝΤΕΡΝΕΤ",
            "ΤΗΛΕΠΙΚΟΙΝΩΝ",
            "ΗΛΕΚΤΡΟΔΟΤ",
            "ΠΡΟΒΛΗΜΑ ΙΝΤΕΡΝΕΤ",
        )
    ):
        return RETRO_AITIOLOGIA_INTERNET
    if "ΣΥΣΤΗΜΑΤΑ" in upper and "ΕΡΓΟΔΟΤΗ" in upper:
        return "002"
    if "ΣΥΝΔΕΣΗΣ" in upper and "ΕΡΓΑΝΗ" in upper:
        return "003"
    if s.isdigit() and s.zfill(3) in AITIOLOGIA_CODES:
        return s.zfill(3)
    raise WorkCardPayloadError(
        f"Μη έγκυρος κωδικός αιτιολογίας: {s}. "
        f"Επιτρεπτοί: {', '.join(sorted(AITIOLOGIA_CODES))}"
    )


def format_f_date_for_ergani(dt: datetime) -> str:
    """Μορφή όπως το εγχειρίδιο: 2022-05-04T01:10:00.7099109+03:00"""
    local = dt.astimezone(tz_athens())
    offset = local.strftime("%z")
    tz = f"{offset[:3]}:{offset[3:]}" if offset else "+03:00"
    frac = f"{local.microsecond:06d}1" if local.microsecond else "0000000"
    return f"{local.strftime('%Y-%m-%dT%H:%M:%S')}.{frac}{tz}"


def build_wrk_card_se_payload(
    *,
    employer_afm: str,
    branch_aa: str,
    employee_afm: str,
    employee_last_name: str,
    employee_first_name: str,
    event: str | None = None,
    f_type: str | None = None,
    comments: str | None = None,
    reference_date: str | None = None,
    event_at: str | None = None,
    aitiologia: str | None = None,
    include_null_aitiologia: bool = False,
) -> dict[str, Any]:
    erg = norm_afm(employer_afm)
    emp = norm_afm(employee_afm)
    ep = (employee_last_name or "").strip()
    on = (employee_first_name or "").strip()
    if not ep or not on:
        raise WorkCardPayloadError("Απαιτούνται επώνυμο και όνομα εργαζομένου")
    aa = (branch_aa or "0").strip()[:32] or "0"
    ft = f_type_from_event(event, f_type)
    dt = parse_event_at(event_at, reference_date)
    ref = (reference_date or "").strip()[:10] or dt.date().isoformat()
    datetime.strptime(ref, "%Y-%m-%d")
    f_date = format_f_date_for_ergani(dt)
    ait = normalize_aitiologia(aitiologia)
    detail: dict[str, Any] = {
        "f_afm": emp,
        "f_eponymo": ep,
        "f_onoma": on,
        "f_type": ft,
        "f_reference_date": ref,
        "f_date": f_date,
    }
    if include_null_aitiologia and not ait:
        detail["f_aitiologia"] = None
    elif ait:
        detail["f_aitiologia"] = ait
    return {
        "Cards": {
            "Card": [
                {
                    "f_afm_ergodoti": erg,
                    "f_aa": aa,
                    "f_comments": (comments or "").strip() or None,
                    "Details": {"CardDetails": [detail]},
                }
            ]
        }
    }
