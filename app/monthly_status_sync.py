"""Συγχρονισμός μηνιαίας κατάστασης (EX_BASE_04)."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from app.ergani_client import ErganiClient
from app.ergani_errors import ergani_failure_detail
from app.ergani_parse import parse_authorized_service_names, parse_monthly_status
from app.http_helpers import json_or_text
from app.karta_log import KartaLogger
from app.repo_monthly_status import replace_monthly_status_for_period


def iter_monthly_status_sync_events(
    ctx: dict[str, Any],
    bearer: str,
    report_year: int,
    report_month: int,
    *,
    run_id: str | None = None,
) -> Iterator[dict[str, Any]]:
    log = KartaLogger(
        "monthly_status_sync",
        store_id=ctx.get("id"),
        store_name=ctx.get("name"),
        run_id=run_id,
        register_run=run_id is None,
    )
    client = ErganiClient(ctx.get("api_base_url"))
    afm = str(ctx["employer_afm"]).strip()
    aa = str(ctx.get("branch_aa") or "0").strip()[:32] or "0"
    year = int(report_year)
    month = int(report_month)

    log.info(
        "Έναρξη συγχρονισμού μηνιαίας κατάστασης",
        report_year=year,
        report_month=month,
        employer_afm=afm,
    )
    yield {
        "event": "progress",
        "message": f"Μηνιαία κατάσταση {month:02d}/{year} (EX_BASE_04)…",
        "step": 0,
        "total": 1,
    }

    params = [
        {"ParameterName": "ReportYear", "ParameterValue": str(year)},
        {"ParameterName": "ReportMonth", "ParameterValue": str(month)},
    ]
    try:
        sl = client.services_list(bearer)
        if sl.ok:
            allowed = parse_authorized_service_names(json_or_text(sl))
            if allowed and "EX_BASE_04" not in allowed:
                detail = (
                    f"Το EX_BASE_04 δεν υπάρχει στο ServicesList του API "
                    f"({', '.join(allowed)}). "
                    "Η κλήση είναι σωστή (ReportYear/ReportMonth)· χρειάζεται ενεργοποίηση του service."
                )
                log.error(detail)
                yield {
                    "event": "done",
                    "success": False,
                    "sync": {"success": False, "detail": detail, "count": 0},
                    "message": detail,
                    "logs": log.tail(200),
                    "error": detail,
                }
                return

        resp = client.execute_service("EX_BASE_04", params, bearer)
        parsed = json_or_text(resp)
        if not resp.ok:
            detail = ergani_failure_detail(resp, "EX_BASE_04")
            log.error(detail)
            yield {
                "event": "done",
                "success": False,
                "sync": {"success": False, "detail": detail, "count": 0},
                "message": detail,
                "logs": log.tail(200),
                "error": detail,
            }
            return

        rows = parse_monthly_status(parsed)
        filtered = [r for r in rows if str(r.get("branch_aa") or "0").strip() == aa]
        if not filtered and rows:
            filtered = rows
        saved = replace_monthly_status_for_period(afm, aa, year, month, filtered)
        detail = f"{saved} εγγραφές για {month:02d}/{year}"
        log.info(detail, count=saved)
        yield {
            "event": "done",
            "success": True,
            "sync": {
                "success": True,
                "detail": detail,
                "count": saved,
                "report_year": year,
                "report_month": month,
            },
            "message": f"Ολοκληρώθηκε — {detail}",
            "logs": log.tail(200),
            "error": None,
        }
    except Exception as ex:
        msg = str(ex)
        log.error(msg)
        yield {
            "event": "done",
            "success": False,
            "sync": {"success": False, "detail": msg, "count": 0},
            "message": msg,
            "logs": log.tail(200),
            "error": msg,
        }
