"""Ενημέρωση συμβάσεων από Μητρώο Εργάνη πριν τον υπολογισμό μισθοδοσίας."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from app.payroll import (
    missing_wage_wait_message,
    payroll_afm_key,
    payroll_employee_display_name,
)


MAX_ENRICH_EMPLOYEES = 500


def parse_enrich_employees(body: dict[str, Any] | None) -> list[dict[str, str]]:
    raw = (body or {}).get("employees") or []
    if not isinstance(raw, list):
        return []
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in raw[:MAX_ENRICH_EMPLOYEES]:
        if not isinstance(item, dict):
            continue
        afm = payroll_afm_key(item.get("employee_afm") or item.get("afm"))
        if not afm or afm in seen:
            continue
        seen.add(afm)
        eponymo = str(item.get("eponymo") or "").strip()[:100]
        onoma = str(item.get("onoma") or "").strip()[:100]
        name = str(item.get("name") or "").strip()[:200]
        row = {
            "employee_afm": afm,
            "eponymo": eponymo,
            "onoma": onoma,
            "name": name or payroll_employee_display_name({
                "employee_afm": afm,
                "eponymo": eponymo,
                "onoma": onoma,
            }),
        }
        out.append(row)
    return out


def iter_payroll_wage_enrich_events(
    ctx: dict[str, Any],
    employees: list[dict[str, Any]],
    *,
    run_id: str | None = None,
) -> Iterator[dict[str, Any]]:
    labels: dict[str, str] = {}
    afms: list[str] = []
    seen: set[str] = set()
    for emp in employees:
        afm = payroll_afm_key(emp.get("employee_afm") or emp.get("afm"))
        if not afm or afm in seen:
            continue
        seen.add(afm)
        afms.append(afm)
        labels[afm] = payroll_employee_display_name(emp)

    total = len(afms)
    if not total:
        yield {
            "event": "done",
            "success": True,
            "sync": {
                "success": True,
                "detail": "Κανένας εργαζόμενος για ενημέρωση",
                "count": 0,
            },
            "message": "Δεν βρέθηκαν εργαζόμενοι χωρίς στοιχεία σύμβασης.",
        }
        return

    yield {
        "event": "progress",
        "message": (
            f"Λείπουν στοιχεία για {total} εργαζομένους. "
            "Ενημέρωση από το Μητρώο Εργάνη… Παρακαλώ περιμένετε."
        ),
        "step": 0,
        "total": total,
    }
    # Άμεσο μήνυμα για τον πρώτο, πριν ανοίξει το portal.
    yield {
        "event": "progress",
        "message": missing_wage_wait_message(labels[afms[0]], step=1, total=total),
        "step": 1,
        "total": total,
    }

    from app.portal_employment_contract_sync import iter_employment_contract_sync_events

    for ev in iter_employment_contract_sync_events(
        ctx,
        run_id=run_id,
        only_afms=afms,
        afm_labels=labels,
    ):
        event = ev.get("event")
        if event == "done":
            result = ev.get("result") or ev.get("sync") or {}
            success = ev.get("success")
            if success is None:
                success = bool(result.get("success"))
            yield {
                "event": "done",
                "success": bool(success),
                "sync": result,
                "message": (
                    ev.get("message")
                    or result.get("detail")
                    or "Ολοκληρώθηκε η ενημέρωση από το Μητρώο."
                ),
            }
            continue
        yield ev
