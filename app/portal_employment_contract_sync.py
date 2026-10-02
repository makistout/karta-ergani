"""
Συγχρονισμός στοιχείων σύμβασης από Ergani Μητρώα
(Mitroa/ErgazomenosSearch.aspx → Ergazomenos.aspx).

Ημερήσιο/χειροκίνητο: στόχος = ωράριο ∩ ενεργοί (+ ορφανές δραστηριότητες).
Opportunistic enrichment: νέες εμφανίσεις στο τρέχον Μητρώο (ανεξάρτητα ωραρίου)
μέσω only_afms από snapshot diff.
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
from app.ergani_parse import parse_ergani_calendar_date
from app.repo_entities import (
    fill_employment_hire_date_if_empty,
    link_employee_to_store,
    list_employees_for_employer,
    list_unlinked_activity_employees,
    update_employment_work_time_qr,
    upsert_employee_by_afm,
)
from app.repo_schedule import list_schedule_employee_afms
from app.work_card_payload import norm_afm


def _norm_afm_or_empty(value: Any) -> str:
    digits = "".join(ch for ch in str(value or "") if ch.isdigit())[:9]
    return digits if len(digits) == 9 else ""

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


def _search_employees(
    session: requests.Session,
    page_html: str,
    page_url: str,
    ctx: dict[str, Any],
    *,
    employee_afm: str = "",
    current_only: bool = True,
    branch_aa: str | None = None,
) -> tuple[str, str]:
    """Αναζήτηση Μητρώου. Κενό branch_aa = όλα τα παραρτήματα."""
    form = _find_search_form(page_html)
    if not form:
        raise RuntimeError("Δεν βρέθηκε φόρμα αναζήτησης προσωπικού")
    data = _extract_aspnet_form_data(page_html, include_text=True)
    if branch_aa is None:
        branch_aa = str(ctx.get("branch_aa") or "0").strip()
    if str(branch_aa).strip() == "":
        data[f"{_SEARCH_CTRL}$PararthmaSelection$PararthmaListEdit"] = ""
    else:
        data[f"{_SEARCH_CTRL}$PararthmaSelection$PararthmaListEdit"] = _pick_pararthma(
            page_html, str(branch_aa)
        )
    for key in (
        "AfmEdit",
        "EponimoBox",
        "NameBox",
        "OnomaPateraBox",
        "ArTaytotitasBox",
    ):
        data[f"{_SEARCH_CTRL}${key}"] = ""
    data[f"{_SEARCH_CTRL}$AfmEdit"] = _norm_afm_or_empty(employee_afm)
    if current_only:
        data[f"{_SEARCH_CTRL}$CurrentBox"] = "on"
    else:
        data.pop(f"{_SEARCH_CTRL}$CurrentBox", None)
    data[f"{_SEARCH_CTRL}$SearchControlSearchButton"] = "Αναζήτηση"
    action = urljoin(page_url, form.get("action") or page_url)
    r = session.post(action, data=data, timeout=REQUEST_TIMEOUT, allow_redirects=True)
    if "error.aspx" in r.url.lower():
        raise RuntimeError("Σφάλμα portal κατά την αναζήτηση προσωπικού")
    return r.text, r.url


def _search_current_employees(
    session: requests.Session,
    page_html: str,
    page_url: str,
    ctx: dict[str, Any],
) -> tuple[str, str]:
    return _search_employees(
        session, page_html, page_url, ctx, current_only=True
    )


def leftover_target_afms(
    target_afms: set[str],
    found_afms: set[str],
    afm_labels: dict[str, str] | None = None,
) -> list[str]:
    missing = {
        key for a in target_afms
        if (key := _norm_afm_or_empty(a)) and key not in found_afms
    }
    missing.discard("")
    if not missing:
        return []
    ordered: list[str] = []
    for afm in (afm_labels or {}):
        key = _norm_afm_or_empty(afm)
        if key in missing and key not in ordered:
            ordered.append(key)
    for afm in sorted(missing):
        if afm not in ordered:
            ordered.append(afm)
    return ordered


def lookup_registry_row_by_afm(
    session: requests.Session,
    ctx: dict[str, Any],
    employee_afm: str,
) -> tuple[str, str, str, str] | None:
    """Καρτέλα Μητρώου ανά ΑΦΜ σε όλα τα παραρτήματα, και μη τρέχοντες."""
    afm = norm_afm(employee_afm)
    if not afm:
        return None
    portal_base = _portal_base(ctx)
    page_html, page_url = _open_search_page(session, portal_base)
    page_html, page_url = _search_employees(
        session,
        page_html,
        page_url,
        ctx,
        employee_afm=afm,
        current_only=False,
        branch_aa="",
    )
    match = next((row for row in parse_search_select_ids(page_html) if row[1] == afm), None)
    if not match:
        return None
    return match[0], match[1], match[2], page_url


def fetch_registry_detail_by_afm(ctx: dict[str, Any], employee_afm: str) -> dict[str, Any] | None:
    """Καρτέλα Μητρώου (και πρώην) για αυτόματο γέμισμα πρόσληψης."""
    session = _login_session(ctx)
    match = lookup_registry_row_by_afm(session, ctx, employee_afm)
    if not match:
        return None
    ergodoti_id, afm, _stamp, page_url = match
    return _fetch_contract_detail(session, page_url, ergodoti_id, afm)


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


def list_current_mitroo_employee_afms(ctx: dict[str, Any]) -> list[str]:
    """Τρέχοντες εργαζόμενοι Μητρώου για το παράρτημα (μόνο λίστα ΑΦΜ, χωρίς καρτέλες)."""
    portal_base = _portal_base(ctx)
    session = _login_session(ctx)
    page_html, page_url = _open_search_page(session, portal_base)
    page_html, page_url = _search_current_employees(
        session, page_html, page_url, ctx
    )
    all_ids = _collect_select_ids(session, page_url, page_html)
    out: list[str] = []
    seen: set[str] = set()
    for _ergodoti_id, afm, _stamp in all_ids:
        value = norm_afm(afm)
        if value and value not in seen:
            seen.add(value)
            out.append(value)
    return out


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


def _persist_contract_from_portal_row(
    *,
    employer_afm: str,
    branch_aa: str,
    afm: str,
    stamp: str,
    row: dict[str, Any],
    unlinked_afms: set[str],
    active_afms: set[str],
) -> dict[str, bool]:
    if not row.get("employee_afm"):
        row["employee_afm"] = afm
    result = insert_if_changed(employer_afm, branch_aa, row)
    flex = row.get("flex_arrival_minutes")
    upsert_employee_by_afm(
        afm,
        row.get("eponymo"),
        row.get("onoma"),
        flex_arrival_minutes=flex,
        amka=row.get("amka"),
        amika=row.get("amika"),
    )
    linked = False
    if (afm in unlinked_afms or afm not in active_afms) and link_employee_to_store(
        employer_afm,
        branch_aa,
        afm,
        row.get("eponymo"),
        row.get("onoma"),
        flex_arrival_minutes=flex,
        amka=row.get("amka"),
        amika=row.get("amika"),
    ):
        linked = True
    qr = False
    if update_employment_work_time_qr(
        employer_afm,
        branch_aa,
        afm,
        qr_data_url=row.get("work_time_qr_data_url"),
    ):
        qr = True
    hire = parse_ergani_calendar_date(row.get("hire_date"))
    stamp_text = str(stamp or "").strip()
    if hire is None and stamp_text and ":" not in stamp_text:
        hire = parse_ergani_calendar_date(stamp_text)
    if hire:
        fill_employment_hire_date_if_empty(employer_afm, branch_aa, afm, hire)
    return {
        "inserted": bool(result.get("inserted")),
        "linked": linked,
        "qr": qr,
    }


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
    only_afms: set[str] | list[str] | None = None,
    afm_labels: dict[str, str] | None = None,
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
    if only_afms is not None:
        target_afms = {norm_afm(a) for a in only_afms}
        target_afms.discard("")
    else:
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
        only_afms=bool(only_afms is not None),
    )
    labeled = bool(afm_labels)
    if labeled:
        yield {
            "event": "progress",
            "message": (
                f"Λείπουν στοιχεία για {len(target_afms)} εργαζομένους. "
                "Ενημέρωση από το Μητρώο Εργάνη… Παρακαλώ περιμένετε."
            ),
            "step": 0,
            "total": max(len(target_afms), 1),
        }
        yield {
            "event": "progress",
            "message": "Ενημέρωση προσωπικών στοιχείων από Μητρώο (EX_BASE_05)… Παρακαλώ περιμένετε.",
            "step": 0,
            "total": max(len(target_afms), 1),
        }
    else:
        yield {
            "event": "progress",
            "message": (
                f"Σύμβαση για ενεργούς στο ψηφιακό ωράριο ({len(target_afms)})…"
                if only_afms is None
                else f"Σύμβαση/QR για {len(target_afms)} εργαζομένους…"
            ),
            "step": 0,
            "total": len(target_afms),
        }
        yield {
            "event": "progress",
            "message": "Ενημέρωση πρόσληψης / ΑΜΚΑ / ΑΜΑ (EX_BASE_05)…",
            "step": 0,
            "total": max(len(target_afms), 1),
        }
    api_personal: dict[str, Any] = {}
    try:
        from app.repo_employment_contract import refresh_personal_from_ex_base_05

        api_personal = refresh_personal_from_ex_base_05(
            ctx, only_afms=target_afms if only_afms is not None else None, log=log
        )
    except Exception as ex:  # noqa: BLE001
        api_personal = {"success": False, "detail": str(ex)}
        log.error(f"Προσωπικά EX_BASE_05: {ex}")

    if not target_afms:
        msg = (
            "Δεν βρέθηκαν ενεργοί εργαζόμενοι στο ψηφιακό ωράριο — "
            "συγχρονίστε πρώτα προσωπικό/ωράριο."
        )
        if api_personal.get("success"):
            msg += (
                f" Ενημερώθηκαν όμως {int(api_personal.get('scanned') or 0)} "
                "εργαζόμενοι από EX_BASE_05 (πρόσληψη / ΑΜΚΑ / ΑΜΑ)."
            )
        log.error(msg)
        yield {"event": "error", "message": msg, "logs": log.tail(100)}
        if finalize_run:
            from app import repo_sync_log

            repo_sync_log.finish_run(
                log.run_id,
                status="error",
                message=msg,
                result={"success": False, "error": msg, "api_personal": api_personal},
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
        detail = str(ex)
        if api_personal.get("success"):
            detail += (
                f" — EX_BASE_05: {int(api_personal.get('scanned') or 0)} εργαζόμενοι "
                "(πρόσληψη / ΑΜΚΑ / ΑΜΑ)"
            )
        yield {"event": "error", "message": detail, "logs": log.tail(100)}
        if finalize_run:
            from app import repo_sync_log

            repo_sync_log.finish_run(
                log.run_id,
                status="error",
                message=detail,
                result={"success": False, "error": str(ex), "api_personal": api_personal},
            )
        return

    total = len(select_ids)
    inserted = 0
    unchanged = 0
    errors: list[str] = []
    linked = 0
    qr_synced = 0

    if not labeled:
        yield {
            "event": "progress",
            "message": (
                f"Στο ωράριο ∩ Μητρώο: {total} "
                f"(αγνοήθηκαν {len(all_ids) - total} εκτός ωραρίου)…"
            ),
            "step": 0,
            "total": total,
        }

    found_afms = {row[1] for row in select_ids}
    leftovers = leftover_target_afms(target_afms, found_afms, afm_labels)
    wait_total = total + len(leftovers)
    if labeled:
        from app.payroll import missing_wage_wait_message

    for i, (ergodoti_id, afm, stamp) in enumerate(select_ids):
        if labeled:
            name = str((afm_labels or {}).get(afm) or "").strip() or f"ΑΦΜ {afm}"
            msg = missing_wage_wait_message(name, step=i + 1, total=wait_total or 1)
        else:
            msg = f"Σύμβαση ΑΦΜ {afm} ({i + 1}/{wait_total or total})…"
        log.info(msg, employee_afm=afm, step=i + 1, total=wait_total or total)
        yield {
            "event": "progress",
            "message": msg,
            "step": i + 1,
            "total": wait_total or total,
        }
        try:
            row = _fetch_contract_detail(session, page_url, ergodoti_id, afm)
            stats = _persist_contract_from_portal_row(
                employer_afm=employer_afm,
                branch_aa=branch_aa,
                afm=afm,
                stamp=stamp,
                row=row,
                unlinked_afms=unlinked_afms,
                active_afms=active_afms,
            )
            if stats["inserted"]:
                inserted += 1
            else:
                unchanged += 1
            if stats["linked"]:
                linked += 1
                log.info(
                    "Συνδέθηκε/ενεργοποιήθηκε εργαζόμενος στο κατάστημα",
                    employee_afm=afm,
                )
            if stats["qr"]:
                qr_synced += 1
        except Exception as ex:  # noqa: BLE001 — συνέχεια με επόμενο εργαζόμενο
            err = f"{afm}: {ex}"
            errors.append(err)
            log.error(err)

    for j, afm in enumerate(leftovers):
        step = total + j + 1
        name = str((afm_labels or {}).get(afm) or "").strip() or f"ΑΦΜ {afm}"
        if labeled:
            msg = missing_wage_wait_message(name, step=step, total=wait_total or 1)
        else:
            msg = (
                f"Αναζήτηση καρτέλας Μητρώου ΑΦΜ {afm} σε όλα τα παραρτήματα "
                f"({step}/{wait_total or 1})…"
            )
        log.info(msg, employee_afm=afm, step=step, total=wait_total)
        yield {
            "event": "progress",
            "message": msg,
            "step": step,
            "total": wait_total or 1,
        }
        try:
            found = lookup_registry_row_by_afm(session, ctx, afm)
            if not found:
                log.info("Δεν βρέθηκε καρτέλα Μητρώου", employee_afm=afm)
                yield {
                    "event": "progress",
                    "message": (
                        f"Δεν βρέθηκε καρτέλα στο Μητρώο για {name}. "
                        "Συνεχίζουμε με τον επόμενο…"
                    ),
                    "step": step,
                    "total": wait_total or 1,
                }
                continue
            ergodoti_id, found_afm, stamp, found_url = found
            row = _fetch_contract_detail(session, found_url, ergodoti_id, found_afm)
            stats = _persist_contract_from_portal_row(
                employer_afm=employer_afm,
                branch_aa=branch_aa,
                afm=found_afm,
                stamp=stamp,
                row=row,
                unlinked_afms=unlinked_afms,
                active_afms=active_afms,
            )
            if stats["inserted"]:
                inserted += 1
            else:
                unchanged += 1
            if stats["linked"]:
                linked += 1
            if stats["qr"]:
                qr_synced += 1
        except Exception as ex:  # noqa: BLE001
            err = f"{afm}: {ex}"
            errors.append(err)
            log.error(err)

    touched = inserted + unchanged
    ok = touched > 0 and len(errors) < max(touched, 1)
    detail = (
        f"{inserted} νέες εκδόσεις, {unchanged} χωρίς αλλαγή"
        f" ({total} ενεργοί ∩ ωράριο ∩ Μητρώο"
        f", {len(target_afms)} στόχος"
        f", {len(all_ids)} στο Μητρώο)"
        + (f" — {len(leftovers)} εκτός τρέχοντος παραρτήματος" if leftovers else "")
        + (f" — {linked} νέες συνδέσεις" if linked else "")
        + (f" — {qr_synced} QR" if qr_synced else "")
        + (f" — {len(errors)} αποτυχίες" if errors else "")
    )
    if api_personal.get("success"):
        detail += (
            f" — προσωπικά EX_BASE_05 {int(api_personal.get('inserted') or 0)} "
            f"νέες εκδόσεις / {int(api_personal.get('scanned') or 0)} εργαζόμενοι"
        )
    elif api_personal.get("detail"):
        detail += f" — προσωπικά EX_BASE_05: {api_personal.get('detail')}"
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
        "api_personal": api_personal,
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
    only_afms: set[str] | list[str] | None = None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "success": False,
        "detail": "Δεν ολοκληρώθηκε",
        "count": 0,
    }
    for ev in iter_employment_contract_sync_events(
        ctx, run_id=run_id, only_afms=only_afms
    ):
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
