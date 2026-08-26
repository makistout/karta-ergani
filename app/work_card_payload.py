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
# Επίσημος κανόνας ΕΡΓΑΝΗ: η δήλωση κάρτας είναι εμπρόθεσμη εντός 15'
# από την καταγραφή του γεγονότος. Μόνο μετά το όριο απαιτείται αιτιολογία.
WRK_CARD_ON_TIME_LIMIT_MINUTES = 15


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


FUTURE_EVENT_AT_ERROR = "Η ώρα κίνησης δεν μπορεί να είναι μελλοντική"


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


def event_at_is_future(dt: datetime, *, now: datetime | None = None) -> bool:
    """Κοινός guard για κάθε κανάλι υποβολής κάρτας εργασίας."""
    event_dt = dt
    if event_dt.tzinfo is None:
        event_dt = event_dt.replace(tzinfo=tz_athens())
    else:
        event_dt = event_dt.astimezone(tz_athens())
    current = (now or datetime.now(tz_athens())).astimezone(tz_athens())
    return event_dt > current


def wrk_card_needs_aitiologia(
    *,
    f_type: str,
    reference_date: str,
    event_at: str | None,
    schedule_hour_from: str | None = None,
    schedule_hour_to: str | None = None,
    flex_arrival_minutes: int | None = None,
    submitted_at: datetime | None = None,
) -> bool:
    """True μόνο όταν η υποβολή γίνεται πάνω από 15' μετά την κίνηση.

    Τα στοιχεία ωραρίου/flex παραμένουν στην υπογραφή για συμβατότητα κλήσεων,
    αλλά δεν επηρεάζουν την εκπρόθεσμη υποβολή WRKCardSE.
    """
    if not event_at:
        return False
    ref = str(reference_date or "").strip()[:10] or str(event_at).strip()[:10]
    event_dt = parse_event_at(event_at, ref or None)
    submitted = (submitted_at or datetime.now(tz_athens())).astimezone(tz_athens())
    event_local = (
        event_dt.astimezone(tz_athens())
        if event_dt.tzinfo
        else event_dt.replace(tzinfo=tz_athens())
    )
    elapsed_seconds = (submitted - event_local).total_seconds()
    return elapsed_seconds > WRK_CARD_ON_TIME_LIMIT_MINUTES * 60


def resolve_wrk_card_aitiologia(
    *,
    f_type: str,
    event_at: str | None,
    reference_date: str | None,
    requested_aitiologia: str | None,
    schedule_hour_from: str | None = None,
    schedule_hour_to: str | None = None,
    flex_arrival_minutes: int | None = None,
    submitted_at: datetime | None = None,
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
        submitted_at=submitted_at,
    ):
        return None

    if requested_aitiologia:
        ait = normalize_aitiologia(requested_aitiologia)
        return ait or RETRO_AITIOLOGIA_INTERNET
    return RETRO_AITIOLOGIA_INTERNET


def aitiologia_for_wrk_card_submit(
    *,
    f_type: str,
    reference_date: str,
    event_at: str,
    employer_afm: str,
    branch_aa: str,
    employee_afm: str,
    requested_aitiologia: str | None = None,
    submitted_at: datetime | None = None,
) -> str | None:
    """Ενιαία απόφαση αιτιολογίας για κάθε κανάλι υποβολής WRKCardSE."""
    return resolve_wrk_card_aitiologia(
        f_type=f_type,
        event_at=event_at,
        reference_date=reference_date,
        requested_aitiologia=requested_aitiologia,
        submitted_at=submitted_at,
    )


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
    if event_at_is_future(dt):
        raise WorkCardPayloadError(FUTURE_EVENT_AT_ERROR)
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
        # Πάντα στοιχείο f_aitiologia: κωδικός ή κενό string (XSD Ergani).
        "f_aitiologia": ait if ait else "",
    }
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
