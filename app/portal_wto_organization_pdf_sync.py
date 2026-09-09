"""
Λήψη PDF δηλώσεων Ψηφιακής Οργάνωσης Χρόνου Εργασίας από portal
(Αναζήτηση — WTO/WorkingTimeOrganizationSearch.aspx → PrintPDF).

Ίδια λογική με WorkCard PDFs: Select(n, 'id|ημ/νία') →
WorkingTimeOrganizationPrintPDF.aspx?id=…&afm=
αποθήκευση σε data/protocol_pdfs/{afm}/{aa}/{ημέρα}/ και upsert στο
karta_ergani_protocol.
"""

from __future__ import annotations

import html as htmllib
import re
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import requests

from app.date_util import format_date_for_ergani
from app.karta_log import logger_for_store
from app.portal_form_util import set_portal_dates
from app.portal_protocol_pdf_match import (
    _safe_filename,
    protocol_pdf_day_dir,
)
from app.portal_schedule_sync import (
    REQUEST_TIMEOUT,
    _extract_aspnet_form_data,
    _find_search_form,
    _has_next_grid_page,
    _login_session,
    _pick_pararthma,
    _portal_base,
)
from app.repo_ergani_protocol import upsert_protocol_rows
from app.work_card_payload import norm_afm, tz_athens

MAX_GRID_PAGES = 40
SEARCH_PATH = "WTO/WorkingTimeOrganizationSearch.aspx"
PRINT_PDF_PATH = "WTO/WorkingTimeOrganizationPrintPDF.aspx"

_CTRL = (
    "ctl00$ctl00$ContentHolder$ContentHolder$WorkingTimeOrganizationSearchControl"
)
_GRID = (
    "ctl00$ctl00$ContentHolder$ContentHolder$WorkingTimeOrganizationSearchControl"
    "$WorkingTimeOrganizationGridControl$Grid$Grid"
)
_DATE_FROM = (
    f"{_CTRL}$DateYpobolisFromEdit",
    "ctl00_ctl00_ContentHolder_ContentHolder_WorkingTimeOrganizationSearchControl_DateYpobolisFromEdit",
)
_DATE_TO = (
    f"{_CTRL}$DateYpobolisToEdit",
    "ctl00_ctl00_ContentHolder_ContentHolder_WorkingTimeOrganizationSearchControl_DateYpobolisToEdit",
)

SELECT_TR_RE = re.compile(
    r"<tr[^>]*>.*?Select\(\s*\d+\s*,\s*'([^']+)'\s*\).*?</tr>",
    re.I | re.S,
)
TD_RE = re.compile(r"<td[^>]*>(.*?)</td>", re.I | re.S)
TAG_RE = re.compile(r"<[^>]+>")
PROTO_RE = re.compile(r"(ΟΡ\d+|OP\d+|ΟΠ\d+)", re.I)


def _norm_wto_protocol(value: str) -> str:
    s = (value or "").strip().upper().replace("OP", "ΟΡ").replace("ΟΠ", "ΟΡ")
    return s[:128]


def _strip_html(raw: str) -> str:
    text = TAG_RE.sub(" ", htmllib.unescape(raw or ""))
    return re.sub(r"\s+", " ", text).strip()


def parse_wto_submit_datetime(text: str) -> datetime | None:
    """π.χ. ``3/8/2026 11:45:26 πμ`` / ``10/8/2026 4:28:10 μμ`` / ``17/07/2024 14:45``."""
    raw = str(text or "").strip()
    if not raw:
        return None
    raw = raw.replace("\u00a0", " ")
    m = re.match(
        r"^(\d{1,2})/(\d{1,2})/(\d{4})\s+(\d{1,2}):(\d{2})(?::(\d{2}))?\s*(πμ|μμ|ΠΜ|ΜΜ|am|pm|AM|PM)?$",
        raw,
        re.I,
    )
    if not m:
        for fmt in ("%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M"):
            try:
                return datetime.strptime(raw, fmt).replace(tzinfo=tz_athens())
            except ValueError:
                continue
        return None
    day, month, year = int(m.group(1)), int(m.group(2)), int(m.group(3))
    hour, minute = int(m.group(4)), int(m.group(5))
    second = int(m.group(6) or 0)
    ampm = (m.group(7) or "").lower()
    if ampm in ("μμ", "μ.μ.", "pm"):
        if hour < 12:
            hour += 12
    elif ampm in ("πμ", "π.μ.", "am"):
        if hour == 12:
            hour = 0
    try:
        return datetime(year, month, day, hour, minute, second, tzinfo=tz_athens())
    except ValueError:
        return None


def submission_code_for_declaration_type(declaration_type: str) -> str:
    text = (declaration_type or "").casefold()
    if "σταθερ" in text:
        return "WTOWeek"
    if "υπερωρ" in text:
        return "WTOOv"
    if "τροποποι" in text or "μεταβαλλ" in text or "ανά ημέρα" in text:
        return "WTODaily"
    return "WTO"


def extract_wto_select_items_from_html(html: str) -> list[dict[str, str]]:
    """Parse Επισκόπηση Select(n, 'portalId|submitText') από το grid."""
    text = htmllib.unescape(html or "")
    items: list[dict[str, str]] = []
    seen: set[str] = set()
    for m in SELECT_TR_RE.finditer(text):
        token = m.group(1)
        parts = [p.strip() for p in token.split("|", 1)]
        if len(parts) < 2:
            continue
        portal_id, submit_text = parts[0], parts[1]
        if not portal_id.isdigit() or portal_id in seen:
            continue
        seen.add(portal_id)
        cells = [_strip_html(td) for td in TD_RE.findall(m.group(0))]
        # [Επισκόπηση, παράρτημα, κατάσταση, είδος, ημ/νία, πρωτόκολλο, εκπρόθεσμο, …]
        branch = cells[1] if len(cells) > 1 else ""
        status = cells[2] if len(cells) > 2 else ""
        dtype = cells[3] if len(cells) > 3 else ""
        protocol = ""
        for cell in cells:
            pm = PROTO_RE.search(cell or "")
            if pm:
                protocol = pm.group(1)
                break
        if not protocol:
            pm = PROTO_RE.search(m.group(0))
            protocol = pm.group(1) if pm else ""
        overdue_text = ""
        for cell in cells:
            low = (cell or "").casefold()
            if low in ("ναι", "όχι", "οχι", "yes", "no"):
                overdue_text = cell
                break
        protocol = _norm_wto_protocol(protocol) if protocol else ""
        if not protocol.startswith("ΟΡ"):
            protocol = _norm_wto_protocol(f"ΟΡ{portal_id}")
        items.append(
            {
                "portal_id": portal_id,
                "submit_text": submit_text,
                "protocol": protocol,
                "branch_aa": branch or "0",
                "submission_status": status,
                "declaration_type": dtype,
                "overdue_text": overdue_text,
            }
        )
    return items


def _open_wto_search(session: requests.Session, portal_base: str) -> tuple[str, str]:
    url = urljoin(portal_base, SEARCH_PATH)
    r = session.get(url, timeout=REQUEST_TIMEOUT, allow_redirects=True)
    if r.status_code >= 400:
        raise RuntimeError(f"Αποτυχία φόρτωσης WTO Search — HTTP {r.status_code}")
    if "WorkingTimeOrganizationSearchControl" not in r.text:
        raise RuntimeError("Η σελίδα WorkingTimeOrganizationSearch δεν φορτώθηκε σωστά")
    return r.text, r.url


def search_wto_items_for_range(
    session: requests.Session,
    page_html: str,
    page_url: str,
    ctx: dict[str, Any],
    date_from_ergani: str,
    date_to_ergani: str,
) -> tuple[list[dict[str, str]], int]:
    form = _find_search_form(page_html)
    if not form:
        raise RuntimeError("Δεν βρέθηκε φόρμα WorkingTimeOrganizationSearch")
    data = _extract_aspnet_form_data(page_html, include_text=True)
    branch_aa = str(ctx.get("branch_aa") or "0").strip()
    data[f"{_CTRL}$PararthmaSelection$PararthmaListEdit"] = _pick_pararthma(
        page_html, branch_aa
    )
    data[f"{_CTRL}$AfmErgazomenoyEdit"] = ""
    data[f"{_CTRL}$ArProtocolEdit"] = ""
    set_portal_dates(
        data,
        page_html,
        date_from_ergani,
        date_to_ergani,
        fallback_from=_DATE_FROM,
        fallback_to=_DATE_TO,
    )
    data[f"{_CTRL}$SearchControlSearchButton"] = "Αναζήτηση"
    action = urljoin(page_url, form.get("action") or page_url)
    r = session.post(action, data=data, timeout=REQUEST_TIMEOUT, allow_redirects=True)
    if r.status_code >= 400:
        raise RuntimeError(f"Αποτυχία αναζήτησης WTO — HTTP {r.status_code}")
    if "error.aspx" in r.url.lower():
        raise RuntimeError("Αποτυχία αναζήτησης WTO — error.aspx")

    seen: set[str] = set()
    items: list[dict[str, str]] = []
    html, url = r.text, r.url
    pages = 0
    while True:
        pages += 1
        new_on_page = 0
        for it in extract_wto_select_items_from_html(html):
            if it["portal_id"] in seen:
                continue
            seen.add(it["portal_id"])
            items.append(it)
            new_on_page += 1
        if pages >= MAX_GRID_PAGES or not _has_next_grid_page(html) or new_on_page == 0:
            break
        data = _extract_aspnet_form_data(html, include_text=True)
        data["__EVENTTARGET"] = _GRID
        data["__EVENTARGUMENT"] = "Page$Next"
        for key in list(data.keys()):
            if key.endswith("$SearchControlSearchButton"):
                del data[key]
        form = _find_search_form(html)
        action = urljoin(url, form.get("action") or url) if form else url
        r = session.post(action, data=data, timeout=REQUEST_TIMEOUT, allow_redirects=True)
        if r.status_code >= 400 or "error.aspx" in r.url.lower():
            break
        html, url = r.text, r.url
    return items, pages


def _download_wto_pdf(
    session: requests.Session,
    portal_base: str,
    portal_id: str,
    dest: Path,
) -> tuple[bool, bool]:
    if dest.exists() and dest.stat().st_size > 1000:
        return True, True
    pdf_url = urljoin(portal_base, f"{PRINT_PDF_PATH}?id={portal_id}&afm=")
    r = session.get(pdf_url, timeout=REQUEST_TIMEOUT, allow_redirects=True)
    body = r.content or b""
    is_pdf = body[:4] == b"%PDF" or "pdf" in (r.headers.get("Content-Type") or "").lower()
    if r.status_code >= 400 or not is_pdf:
        return False, False
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(body)
    return True, False


def _item_day_iso(item: dict[str, str]) -> str:
    dt = parse_wto_submit_datetime(item.get("submit_text") or "")
    if dt:
        return dt.date().isoformat()
    return date.today().isoformat()


def _norm_branch_aa(value: str | None) -> str:
    return str(value or "0").strip() or "0"


def _rows_for_upsert(
    items: list[dict[str, str]],
    *,
    employer_afm: str,
    branch_aa: str,
) -> list[dict[str, Any]]:
    erg = norm_afm(employer_afm)
    default_aa = _norm_branch_aa(branch_aa)
    out: list[dict[str, Any]] = []
    for it in items:
        row_branch = _norm_branch_aa(it.get("branch_aa") or default_aa)
        if row_branch != default_aa:
            continue
        protocol = _norm_wto_protocol(it.get("protocol") or "")
        if not protocol:
            continue
        overdue_raw = str(it.get("overdue_text") or "").strip().casefold()
        overdue: bool | None
        if overdue_raw in ("ναι", "yes", "1", "true"):
            overdue = True
        elif overdue_raw in ("όχι", "οχι", "no", "0", "false"):
            overdue = False
        else:
            overdue = None
        dtype = str(it.get("declaration_type") or "").strip()
        out.append(
            {
                "employer_afm": erg,
                "branch_aa": default_aa[:32],
                "submission_code": submission_code_for_declaration_type(dtype),
                "protocol": protocol,
                "submit_date_text": (it.get("submit_text") or "")[:128] or None,
                "submit_at": parse_wto_submit_datetime(it.get("submit_text") or ""),
                "submission_status": (it.get("submission_status") or "").strip()[:64] or None,
                "declaration_type": dtype[:256] or None,
                "overdue": overdue,
                "source": "portal_wto_pdf",
            }
        )
    return out


def process_wto_pdfs_for_range(
    *,
    session: requests.Session,
    portal_base: str,
    page_html: str,
    page_url: str,
    ctx: dict[str, Any],
    from_iso: str,
    to_iso: str,
    skip_download_existing: bool = True,
) -> dict[str, Any]:
    t0 = time.perf_counter()
    employer = str(ctx.get("employer_afm") or "")
    branch = str(ctx.get("branch_aa") or "0").strip() or "0"
    result: dict[str, Any] = {
        "from": from_iso[:10],
        "to": to_iso[:10],
        "items": 0,
        "pages": 0,
        "items_skipped_other_branch": 0,
        "pdf_ok": 0,
        "pdf_fail": 0,
        "pdf_skipped_existing": 0,
        "upserted": 0,
        "inserted": 0,
        "updated": 0,
        "error": "",
        "total_s": None,
    }
    try:
        items, pages = search_wto_items_for_range(
            session,
            page_html,
            page_url,
            ctx,
            format_date_for_ergani(from_iso),
            format_date_for_ergani(to_iso),
        )
        want_branch = _norm_branch_aa(branch)
        before = len(items)
        items = [
            it
            for it in items
            if _norm_branch_aa(it.get("branch_aa") or want_branch) == want_branch
        ]
        result["items"] = len(items)
        result["pages"] = pages
        result["items_skipped_other_branch"] = max(0, before - len(items))
    except Exception as ex:
        result["error"] = f"search: {ex}"
        result["total_s"] = round(time.perf_counter() - t0, 3)
        return result

    for it in items:
        day_iso = _item_day_iso(it)
        out_dir = protocol_pdf_day_dir(employer, branch, day_iso)
        label = it.get("protocol") or f"ΟΡ{it['portal_id']}"
        path = out_dir / _safe_filename(f"{label}_{it['portal_id']}.pdf")
        try:
            if skip_download_existing and path.exists() and path.stat().st_size > 1000:
                result["pdf_skipped_existing"] += 1
                result["pdf_ok"] += 1
                continue
            ok, skipped = _download_wto_pdf(session, portal_base, it["portal_id"], path)
            if ok:
                result["pdf_ok"] += 1
                if skipped:
                    result["pdf_skipped_existing"] += 1
            else:
                result["pdf_fail"] += 1
        except Exception:
            result["pdf_fail"] += 1

    rows = _rows_for_upsert(items, employer_afm=employer, branch_aa=branch)
    store_id = int(ctx.get("id") or ctx.get("store_id") or 0)
    if store_id and rows:
        stats = upsert_protocol_rows(store_id, rows)
        result["inserted"] = int(stats.get("inserted") or 0)
        result["updated"] = int(stats.get("updated") or 0)
        result["upserted"] = int(stats.get("total") or 0)

    result["total_s"] = round(time.perf_counter() - t0, 3)
    return result


def sync_wto_organization_pdfs_from_portal(
    ctx: dict[str, Any],
    *,
    from_iso: str,
    to_iso: str,
    session: requests.Session | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    """Κατέβασμα PDF ΟΧΕ + καταχώρηση στο karta_ergani_protocol για διάστημα ημερών."""
    log = logger_for_store("wto_org_pdf", ctx, run_id=run_id)
    portal_base = _portal_base(ctx)
    own_session = session is None
    sess = session or _login_session(ctx)
    t0 = time.perf_counter()
    try:
        page_html, page_url = _open_wto_search(sess, portal_base)
        row = process_wto_pdfs_for_range(
            session=sess,
            portal_base=portal_base,
            page_html=page_html,
            page_url=page_url,
            ctx=ctx,
            from_iso=from_iso,
            to_iso=to_iso,
        )
        log.info(
            f"WTO PDF {row.get('from')}…{row.get('to')}: items={row.get('items')} "
            f"pdf_ok={row.get('pdf_ok')} upserted={row.get('upserted')} "
            f"total={row.get('total_s')}s",
            **{k: v for k, v in row.items() if k != "error" or v},
        )
        return {
            "ok": not bool(row.get("error")),
            "detail": (
                f"ΟΧΕ PDF: {row.get('pdf_ok')}/{row.get('items')} · "
                f"upsert {row.get('upserted')}"
                if not row.get("error")
                else str(row.get("error"))
            ),
            **row,
            "wall_seconds": round(time.perf_counter() - t0, 3),
        }
    finally:
        if own_session:
            try:
                sess.close()
            except Exception:
                pass
