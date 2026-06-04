"""Κατασκευή σώματος POST Documents/WRKCardSE."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import Any

from zoneinfo import ZoneInfo

SUBMISSION_CODE_WRK_CARD = "WRKCardSE"


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
    f_date = dt.isoformat(timespec="milliseconds")
    detail: dict[str, Any] = {
        "f_afm": emp,
        "f_eponymo": ep,
        "f_onoma": on,
        "f_type": ft,
        "f_reference_date": ref,
        "f_date": f_date,
        "f_aitiologia": (aitiologia or "").strip() or None,
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
