"""
Συγχρονισμός στοιχείων σύμβασης από Ergani Μητρώα
(Mitroa/ErgazomenosSearch.aspx → Ergazomenos.aspx).

Μόνο εργαζόμενοι που εμφανίζονται στο τοπικό ψηφιακό ωράριο (karta_schedule).
"""

from __future__ import annotations

from typing import Any, Iterator
from urllib.parse import urljoin

import requests

from app.employment_contract_parse import (
    parse_employment_contract_html,
    parse_search_select_ids,
)
from app.karta_log import logger_for_store
from app.portal_schedule_sync import (
    REQUEST_TIMEOUT,
    _FormParser,
    _extract_aspnet_form_data,
    _has_next_grid_page,
    _login_session,
    _pick_pararthma,
    _portal_base,
)
from app.repo_employment_contract import insert_if_changed
from app.repo_entities import (
    link_employee_to_store,
    list_employees_for_employer,
    list_unlinked_activity_employees,
    update_employment_work_time_qr,
    upsert_employee_by_afm,
)
from app.repo_schedule import list_schedule_employee_afms
from app.work_card_payload import norm_afm

SEARCH_PATH = "Mitroa/ErgazomenosSearch.aspx"
_SEARCH_CTRL = "ctl00$ctl00$ContentHolder$ContentHolder$ErgazomenosSearchControl"
GRID_EVENT_TARGET = f"{_SEARCH_CTRL}$ErgazomenosGridControl$Grid$Grid"
MAX_GRID_PAGES = 80


def _find_search_form(html: str) -> dict | None:
    p = _FormParser()
    p.feed(html)
    for f in p.forms:
        if "ErgazomenosSearchControl" in " ".join(
            i.get("name") or "" for i in f.get("inputs", [])
        ):
            return f
    return p.forms[0] if p.forms else None


def _open_search_page(session: requests.Session, portal_base: str) -> tuple[str, str]:
    r = session.get(urljoin(portal_base, SEARCH_PATH), timeout=REQUEST_TIMEOUT)
    if "ErgazomenosSearchControl" not in r.text:
        raise RuntimeError("Δεν φορτώθηκε η σελίδα Στοιχεία προσωπικού (Μητρώα)")
    return r.text, r.url


def _search_current_employees(
    session: requests.Session,
    page_html: str,
    page_url: str,
    ctx: dict[str, Any],
) -> tuple[str, str]:
    form = _find_search_form(page_html)
    if not form:
        raise RuntimeError("Δεν βρέθηκε φόρμα αναζήτησης προσωπικού")
    data = _extract_aspnet_form_data(page_html, include_text=True)
    branch_aa = str(ctx.get("branch_aa") or "0").strip()
    data[f"{_SEARCH_CTRL}$PararthmaSelection$PararthmaListEdit"] = _pick_pararthma(
        page_html, branch_aa
    )
    for key in (
        "AfmEdit",
        "EponimoBox",
        "NameBox",
        "OnomaPateraBox",
        "ArTaytotitasBox",
    ):
        data[f"{_SEARCH_CTRL}${key}"] = ""
    data[f"{_SEARCH_CTRL}$CurrentBox"] = "on"
    data[f"{_SEARCH_CTRL}$SearchControlSearchButton"] = "Αναζήτηση"
    action = urljoin(page_url, form.get("action") or page_url)
    r = session.post(action, data=data, timeout=REQUEST_TIMEOUT, allow_redirects=True)
    if "error.aspx" in r.url.lower():
        raise RuntimeError("Σφάλμα portal κατά την αναζήτηση προσωπικού")
    return r.text, r.url


def _collect_select_ids(
    session: requests.Session,
    start_url: str,
    first_html: str,
) -> list[tuple[str, str, str]]:
    all_ids = parse_search_select_ids(first_html)
    html = first_html
    url = start_url
    pages = 1
    while _has_next_grid_page(html) and pages < MAX_GRID_PAGES:
        fp = _FormParser()
        fp.feed(html)
        if not fp.forms:
            break
        action = urljoin(url, fp.forms[0].get("action") or url)
        data = _extract_aspnet_form_data(html, include_text=True)
        data["__EVENTTARGET"] = GRID_EVENT_TARGET
        data["__EVENTARGUMENT"] = "Page$Next"
        for key in list(data.keys()):
            if key.endswith("$SearchControlSearchButton"):
                del data[key]
        r = session.post(action, data=data, timeout=REQUEST_TIMEOUT, allow_redirects=True)
        if "error.aspx" in r.url.lower():
            break
        page_ids = parse_search_select_ids(r.text)
        if not page_ids:
            break
        existing = {a for _, a, _ in all_ids}
        for row in page_ids:
            if row[1] not in existing:
                all_ids.append(row)
                existing.add(row[1])
        html, url = r.text, r.url
        pages += 1
    return all_ids


def _fetch_contract_detail(
    session: requests.Session,
    search_url: str,
    ergodoti_id: str,
    employee_afm: str,
) -> dict[str, Any]:
    detail_url = urljoin(
        search_url,
        f"Ergazomenos.aspx?ergodotiId={ergodoti_id}&afm={employee_afm}",
    )
    r = session.get(detail_url, timeout=REQUEST_TIMEOUT, allow_redirects=True)
    if "error.aspx" in r.url.lower() or "ΣΤΟΙΧΕΙΑ ΕΡΓΑΣΙΑΚΗΣ" not in r.text:
        raise RuntimeError(f"Αποτυχία φόρτωσης καρτέλας ΑΦΜ {employee_afm}")
    row = parse_employment_contract_html(r.text, employee_afm=employee_afm)
    qr_src = str(row.get("work_time_qr_src") or "").strip()
    if qr_src:
        try:
            row["work_time_qr_data_url"] = _qr_src_to_data_url(session, r.url, qr_src)
        except requests.RequestException:
            row["work_time_qr_data_url"] = None
    return row


def _qr_src_to_data_url(
    session: requests.Session,
    page_url: str,
    src: str,
) -> str | None:
    """Μετατρέπει QR src του portal σε self-contained data URL για το UI."""
    raw = (src or "").strip()
    if not raw:
        return None
    if raw.lower().startswith("data:image/"):
        return raw
    url = urljoin(page_url, raw)
    r = session.get(url, timeout=REQUEST_TIMEOUT, allow_redirects=True)
    r.raise_for_status()
    content_type = (r.headers.get("Content-Type") or "").split(";", 1)[0].strip().lower()
    if not content_type.startswith("image/"):
        return None
    import base64

    encoded = base64.b64encode(r.content).decode("ascii")
    return f"data:{content_type};base64,{encoded}"


def iter_employment_contract_sync_events(
    ctx: dict[str, Any],
    *,
    run_id: str | None = None,
) -> Iterator[dict[str, Any]]:
    log = logger_for_store("employment_contract_sync", ctx, run_id=run_id)
    finalize_run = run_id is None
    portal_base = _portal_base(ctx)
    employer_afm = str(ctx.get("employer_afm") or "").strip()
    branch_aa = str(ctx.get("branch_aa") or "0").strip() or "0"

    schedule_afms = set(list_schedule_employee_afms(employer_afm, branch_aa))
    active_afms = {
        norm_afm(e.get("afm") or "")
        for e in list_employees_for_employer(employer_afm, branch_aa, active_only=True)
    }
    active_afms.discard("")
    unlinked_rows = list_unlinked_activity_employees(employer_afm, branch_aa)
    unlinked_afms = {
        norm_afm(row.get("afm") or "") for row in unlinked_rows
    }
    unlinked_afms.discard("")
    # Κανονικοί στόχοι + ορφανές δραστηριότητες. Η σύνδεση των ορφανών γίνεται
    # μόνο αν το ΑΦΜ επιβεβαιωθεί από την αναζήτηση τρέχοντος προσωπικού Μητρώου.
    target_afms = (schedule_afms & active_afms if active_afms else schedule_afms) | unlinked_afms
    log.info(
        "Έναρξη συγχρονισμού στοιχείων σύμβασης",
        portal_base=portal_base,
        employer_afm=employer_afm,
        branch_aa=branch_aa,
        schedule_employees=len(schedule_afms),
        active_employees=len(active_afms),
        target_employees=len(target_afms),
        unlinked_activity_employees=len(unlinked_afms),
    )
    yield {
        "event": "progress",
        "message": (
            f"Σύμβαση για ενεργούς στο ψηφιακό ωράριο ({len(target_afms)})…"
        ),
        "step": 0,
        "total": len(target_afms),
    }

    if not target_afms:
        msg = (
            "Δεν βρέθηκαν ενεργοί εργαζόμενοι στο ψηφιακό ωράριο — "
            "συγχρονίστε πρώτα προσωπικό/ωράριο."
        )
        log.error(msg)
        yield {"event": "error", "message": msg, "logs": log.tail(100)}
        if finalize_run:
            from app import repo_sync_log

            repo_sync_log.finish_run(
                log.run_id,
                status="error",
                message=msg,
                result={"success": False, "error": msg},
            )
        return

    try:
        session = _login_session(ctx)
        page_html, page_url = _open_search_page(session, portal_base)
        page_html, page_url = _search_current_employees(
            session, page_html, page_url, ctx
        )
        all_ids = _collect_select_ids(session, page_url, page_html)
        select_ids = [row for row in all_ids if row[1] in target_afms]
        skipped_registry = len(all_ids) - len(select_ids)
        log.info(
            "Αναζήτηση προσωπικού — OK",
            registry_employees=len(all_ids),
            target_match=len(select_ids),
            skipped_not_in_target=skipped_registry,
        )
    except (requests.RequestException, ValueError, RuntimeError) as ex:
        log.error(f"Αποτυχία σύνδεσης/αναζήτησης: {ex}")
        yield {"event": "error", "message": str(ex), "logs": log.tail(100)}
        if finalize_run:
            from app import repo_sync_log

            repo_sync_log.finish_run(
                log.run_id,
                status="error",
                message=str(ex),
                result={"success": False, "error": str(ex)},
            )
        return

    total = len(select_ids)
    inserted = 0
    unchanged = 0
    errors: list[str] = []
    linked = 0
    qr_synced = 0

    yield {
        "event": "progress",
        "message": (
            f"Στο ωράριο ∩ Μητρώο: {total} "
            f"(αγνοήθηκαν {len(all_ids) - total} εκτός ωραρίου)…"
        ),
        "step": 0,
        "total": total,
    }

    for i, (ergodoti_id, afm, _stamp) in enumerate(select_ids):
        msg = f"Σύμβαση ΑΦΜ {afm} ({i + 1}/{total})…"
        log.info(msg, employee_afm=afm, step=i + 1, total=total)
        yield {
            "event": "progress",
            "message": msg,
            "step": i + 1,
            "total": total,
        }
        try:
            row = _fetch_contract_detail(session, page_url, ergodoti_id, afm)
            if not row.get("employee_afm"):
                row["employee_afm"] = afm
            result = insert_if_changed(employer_afm, branch_aa, row)
            if result.get("inserted"):
                inserted += 1
            else:
                unchanged += 1
            flex = row.get("flex_arrival_minutes")
            upsert_employee_by_afm(
                afm,
                row.get("eponymo"),
                row.get("onoma"),
                flex_arrival_minutes=flex,
            )
            if afm in unlinked_afms and link_employee_to_store(
                employer_afm,
                branch_aa,
                afm,
                row.get("eponymo"),
                row.get("onoma"),
                flex_arrival_minutes=flex,
            ):
                linked += 1
                log.info("Συνδέθηκε ορφανή δραστηριότητα με το κατάστημα", employee_afm=afm)
            if update_employment_work_time_qr(
                employer_afm,
                branch_aa,
                afm,
                qr_data_url=row.get("work_time_qr_data_url"),
            ):
                qr_synced += 1
        except Exception as ex:  # noqa: BLE001 — συνέχεια με επόμενο εργαζόμενο
            err = f"{afm}: {ex}"
            errors.append(err)
            log.error(err)

    ok = total > 0 and len(errors) < total
    detail = (
        f"{inserted} νέες εκδόσεις, {unchanged} χωρίς αλλαγή"
        f" ({total} ενεργοί ∩ ωράριο ∩ Μητρώο"
        f", {len(target_afms)} στόχος"
        f", {len(all_ids)} στο Μητρώο)"
        + (f" — {linked} νέες συνδέσεις" if linked else "")
        + (f" — {qr_synced} QR" if qr_synced else "")
        + (f" — {len(errors)} αποτυχίες" if errors else "")
    )
    result = {
        "success": ok,
        "detail": detail,
        "count": inserted,
        "unchanged": unchanged,
        "employees": total,
        "target_employees": len(target_afms),
        "schedule_employees": len(schedule_afms),
        "active_employees": len(active_afms),
        "registry_employees": len(all_ids),
        "unlinked_activity_employees": len(unlinked_afms),
        "linked_employees": linked,
        "qr_synced": qr_synced,
        "skipped_not_in_target": len(all_ids) - total,
        "errors": errors[:30],
        "logs": log.tail(100),
        "source": "portal",
        "portal_base": portal_base,
        "employer_afm": employer_afm,
        "branch_aa": branch_aa,
    }
    log.info(
        "Ολοκλήρωση συγχρονισμού σύμβασης",
        success=ok,
        inserted=inserted,
        unchanged=unchanged,
        qr_synced=qr_synced,
        errors=len(errors),
    )
    if finalize_run:
        from app import repo_sync_log

        repo_sync_log.finish_run(
            log.run_id,
            status="ok" if ok else "error",
            message=detail,
            result=result,
        )
    yield {"event": "done", "result": result}


def sync_employment_contracts_from_portal(
    ctx: dict[str, Any],
    *,
    run_id: str | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "success": False,
        "detail": "Δεν ολοκληρώθηκε",
        "count": 0,
    }
    for ev in iter_employment_contract_sync_events(ctx, run_id=run_id):
        if ev.get("event") == "done":
            result = ev.get("result") or result
        elif ev.get("event") == "error":
            result = {
                "success": False,
                "detail": ev.get("message") or "Σφάλμα",
                "count": 0,
                "logs": ev.get("logs"),
            }
    return result
