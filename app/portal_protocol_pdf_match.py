"""
Λήψη PDF δηλώσεων WorkCard από portal + αντιστοίχιση στην πραγματική.

Από το περιεχόμενο PDF (ενότητες ΩΡΑ ΠΡΟΣΕΛΕΥΣΗΣ / ΩΡΑ ΑΠΟΧΩΡΗΣΗΣ): αν υπάρχει
γραμμή δεδομένων κάτω από την επικεφαλίδα → ΑΦΜ + ώρα → protocol_from / protocol_to
στο karta_work_log (μόνο κενά πεδία).
"""

from __future__ import annotations

import re
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import requests

from app.date_util import format_date_for_ergani
from app.db import cursor
from app.karta_log import logger_for_store
from app.portal_card_protocol_sync import (
    _CTRL,
    _DATE_FROM_FALLBACK,
    _DATE_TO_FALLBACK,
    _GRID,
    _open_work_card_search,
)
from app.portal_form_util import set_portal_dates
from app.portal_schedule_sync import (
    REQUEST_TIMEOUT,
    _extract_aspnet_form_data,
    _find_search_form,
    _has_next_grid_page,
    _login_session,
    _pick_pararthma,
    _portal_base,
)
from app.work_card_payload import norm_afm
from config import Config

MAX_GRID_PAGES = 40
PRINT_PDF_PATH = "WTO/WorkCard/WorkCardPrintPDF.aspx"

SELECT_RE = re.compile(
    r"Select\(\s*\d+\s*,\s*(?:'|&#39;|&apos;)([^'&]+)(?:'|&#39;|&apos;)\s*\)",
    re.I,
)
TR_RE = re.compile(
    r"<tr[^>]*>.*?Select\(\s*\d+\s*,\s*(?:'|&#39;|&apos;)([^'&]+)(?:'|&#39;|&apos;)\s*\).*?</tr>",
    re.I | re.S,
)
PROTOCOL_RE = re.compile(r"(Κ[ΕE]\d{6,}|KE\d{6,})", re.I)
PIPE_RE = re.compile(r"(\d{6,})\|(\d{12,})\|([^'\"&<]{0,80})")
PDF_ROW_RE = re.compile(
    r"(?<!\d)(\d{9})\s+([Α-ΩA-ZΆ-ΏΪΫά-ώϊϋΐΰ\-\s]+?)\s+(\d{2}/\d{2}/\d{4})\s+(\d{1,2}:\d{2})",
    re.I,
)


def protocol_pdf_day_dir(
    employer_afm: str,
    branch_aa: str,
    day_iso: str,
    *,
    root: Path | None = None,
) -> Path:
    base = root or Config.PROTOCOL_PDF_DIR
    return (
        base
        / str(employer_afm or "").strip()
        / (str(branch_aa or "0").strip() or "0")
        / str(day_iso).strip()[:10]
    )


def find_protocol_pdf_path(
    employer_afm: str,
    branch_aa: str,
    day_iso: str,
    protocol: str,
    *,
    root: Path | None = None,
) -> Path | None:
    """Βρίσκει τοπικό PDF δήλωσης για πρωτόκολλο (όνομα ``ΚΕ…_portalId.pdf``)."""
    proto = _norm_protocol(protocol)
    if not proto:
        return None
    day_dir = protocol_pdf_day_dir(employer_afm, branch_aa, day_iso, root=root)
    if not day_dir.is_dir():
        return None
    for path in day_dir.glob("*.pdf"):
        stem = path.stem
        prefix = stem.split("_", 1)[0]
        if _norm_protocol(prefix) == proto and path.stat().st_size > 1000:
            return path
    return None


def index_protocol_pdfs_for_range(
    employer_afm: str,
    branch_aa: str,
    from_iso: str,
    to_iso: str,
    *,
    root: Path | None = None,
) -> set[str]:
    """Σύνολο κανονικοποιημένων πρωτοκόλλων με υπάρχον PDF στο διάστημα ημερών."""
    start = datetime.strptime(str(from_iso)[:10], "%Y-%m-%d").date()
    end = datetime.strptime(str(to_iso)[:10], "%Y-%m-%d").date()
    if start > end:
        start, end = end, start
    found: set[str] = set()
    day = start
    while day <= end:
        day_dir = protocol_pdf_day_dir(
            employer_afm, branch_aa, day.isoformat(), root=root
        )
        if day_dir.is_dir():
            for path in day_dir.glob("*.pdf"):
                if path.stat().st_size <= 1000:
                    continue
                prefix = path.stem.split("_", 1)[0]
                proto = _norm_protocol(prefix)
                if proto:
                    found.add(proto)
        day += timedelta(days=1)
    return found


def _norm_hm(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    if "T" in raw or " " in raw:
        raw = raw.replace("T", " ").split()[-1]
    parts = raw.split(":")
    if len(parts) < 2:
        return raw[:5]
    try:
        return f"{int(parts[0]):02d}:{parts[1][:2]}"
    except ValueError:
        return raw[:5]


def _norm_protocol(value: str) -> str:
    s = (value or "").strip().upper().replace("KE", "ΚΕ")
    s = s.replace("OP", "ΟΡ").replace("ΟΠ", "ΟΡ")
    return s[:128]


def _safe_filename(s: str) -> str:
    return re.sub(r"[^\w.\-Α-Ωα-ωΆ-Ώά-ώ]+", "_", s, flags=re.I)


def _parse_select_token(token: str) -> dict[str, str] | None:
    parts = [p.strip() for p in str(token).split("|")]
    if len(parts) < 2:
        return None
    portal_id, date_submitted = parts[0], parts[1]
    if not portal_id.isdigit() or not date_submitted.isdigit():
        return None
    return {
        "portal_id": portal_id,
        "date_submitted": date_submitted,
        "submit_text": parts[2] if len(parts) > 2 else "",
    }


def extract_select_items_from_html(html: str) -> list[dict[str, str]]:
    """Parse Select(n, 'id|dateSubmitted|…') από HTML αποτελέσματα WorkCardSearch."""
    items: list[dict[str, str]] = []
    seen: set[str] = set()

    def _add(parsed: dict[str, str], proto: str = "") -> None:
        key = f"{parsed['portal_id']}|{parsed['date_submitted']}"
        if key in seen:
            return
        seen.add(key)
        parsed = dict(parsed)
        parsed["protocol"] = _norm_protocol(proto or parsed.get("protocol") or "")
        items.append(parsed)

    for m in TR_RE.finditer(html or ""):
        parsed = _parse_select_token(m.group(1))
        if not parsed:
            continue
        proto_m = PROTOCOL_RE.search(m.group(0))
        proto = _norm_protocol(proto_m.group(1)) if proto_m else ""
        _add(parsed, proto)
    if items:
        return items
    for m in SELECT_RE.finditer(html or ""):
        parsed = _parse_select_token(m.group(1))
        if parsed:
            _add(parsed)
    if items:
        return items
    for m in PIPE_RE.finditer(html or ""):
        _add(
            {
                "portal_id": m.group(1),
                "date_submitted": m.group(2),
                "submit_text": m.group(3).strip(),
                "protocol": "",
            }
        )
    return items


def parse_protocol_pdf_text(text: str, *, filename: str = "") -> dict[str, Any]:
    """
    Εξαγωγή γραμμής προσέλευσης / αποχώρησης από κείμενο PDF δήλωσης.

    Επιστρέφει protocol + in_row / out_row (ή None αν η ενότητα είναι κενή).
    """
    body = text or ""
    in_pos = body.find("ΠΡΟΣΕΛΕΥΣΗΣ")
    out_pos = body.find("ΑΠΟΧΩΡΗΣΗΣ")
    in_row: dict[str, str] | None = None
    out_row: dict[str, str] | None = None

    for m in PDF_ROW_RE.finditer(body):
        item = {
            "afm": m.group(1),
            "name": " ".join(m.group(2).split()),
            "day": m.group(3),
            "time": _norm_hm(m.group(4)),
        }
        pos = m.start()
        if out_pos >= 0 and pos > out_pos:
            out_row = item
        elif in_pos >= 0 and pos > in_pos and (out_pos < 0 or pos < out_pos):
            in_row = item

    proto = ""
    pm = PROTOCOL_RE.search(filename or "")
    if pm:
        proto = _norm_protocol(pm.group(1))
    if not proto:
        pm = PROTOCOL_RE.search(body)
        if pm:
            proto = _norm_protocol(pm.group(1))

    return {
        "protocol": proto,
        "in_row": in_row,
        "out_row": out_row,
        "has_in_header": in_pos >= 0,
        "has_out_header": out_pos >= 0,
    }


def parse_protocol_pdf_file(path: Path) -> dict[str, Any]:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    text = "\n".join((page.extract_text() or "") for page in reader.pages)
    return parse_protocol_pdf_text(text, filename=path.name)


def search_workcard_items_for_day(
    session: requests.Session,
    page_html: str,
    page_url: str,
    ctx: dict[str, Any],
    day_ergani: str,
) -> tuple[list[dict[str, str]], int]:
    """Αναζήτηση μίας ημέρας + pagination grid (page size ~20)."""
    form = _find_search_form(page_html)
    if not form:
        raise RuntimeError("Δεν βρέθηκε φόρμα WorkCardSearch")
    data = _extract_aspnet_form_data(page_html, include_text=True)
    branch_aa = str(ctx.get("branch_aa") or "0").strip()
    data[f"{_CTRL}$PararthmaSelection$PararthmaListEdit"] = _pick_pararthma(page_html, branch_aa)
    data[f"{_CTRL}$AfmErgazomenoyEdit"] = ""
    data[f"{_CTRL}$ArProtocolEdit"] = ""
    set_portal_dates(
        data,
        page_html,
        day_ergani,
        day_ergani,
        fallback_from=_DATE_FROM_FALLBACK,
        fallback_to=_DATE_TO_FALLBACK,
    )
    data[f"{_CTRL}$SearchControlSearchButton"] = "Αναζήτηση"
    action = urljoin(page_url, form.get("action") or page_url)
    r = session.post(action, data=data, timeout=REQUEST_TIMEOUT, allow_redirects=True)
    if r.status_code >= 400:
        raise RuntimeError(f"Αποτυχία αναζήτησης WorkCardSearch — HTTP {r.status_code}")
    if "error.aspx" in r.url.lower():
        raise RuntimeError("Αποτυχία αναζήτησης WorkCardSearch — error.aspx")

    seen: set[str] = set()
    items: list[dict[str, str]] = []
    html, url = r.text, r.url
    pages = 0
    while True:
        pages += 1
        new_on_page = 0
        for it in extract_select_items_from_html(html):
            key = f"{it['portal_id']}|{it['date_submitted']}"
            if key in seen:
                continue
            seen.add(key)
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


def _download_pdf(
    session: requests.Session,
    portal_base: str,
    item: dict[str, str],
    dest: Path,
) -> tuple[bool, bool]:
    """Επιστρέφει (ok, skipped_existing)."""
    if dest.exists() and dest.stat().st_size > 1000:
        return True, True
    pdf_url = urljoin(
        portal_base,
        f"{PRINT_PDF_PATH}?id={item['portal_id']}&dateSubmitted={item['date_submitted']}&afm=",
    )
    r = session.get(pdf_url, timeout=REQUEST_TIMEOUT, allow_redirects=True)
    body = r.content or b""
    is_pdf = body[:4] == b"%PDF" or "pdf" in (r.headers.get("Content-Type") or "").lower()
    if r.status_code >= 400 or not is_pdf:
        return False, False
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(body)
    return True, False


def _work_log_rows_for_day(
    employer_afm: str,
    branch_aa: str,
    day_iso: str,
) -> list[dict[str, Any]]:
    afm = str(employer_afm or "").strip()
    aa = str(branch_aa or "0").strip() or "0"
    day = str(day_iso).strip()[:10]
    day_ergani = format_date_for_ergani(day)
    sql = """
        SELECT id, employee_afm, hour_from, hour_to, protocol_from, protocol_to, work_date
        FROM dbo.karta_work_log
        WHERE employer_afm = ?
          AND branch_aa = ?
          AND (
            work_date = ?
            OR TRY_CONVERT(date, work_date, 103) = ?
            OR CONVERT(varchar(10), TRY_CONVERT(date, work_date, 23), 23) = ?
          )
    """
    with cursor(commit=False) as cur:
        cur.execute(sql, (afm, aa, day_ergani, day, day))
        cols = [d[0] for d in cur.description]
        return [dict(zip(cols, row)) for row in cur.fetchall()]


def apply_pdf_content_matches(
    *,
    employer_afm: str,
    branch_aa: str,
    day_iso: str,
    parsed_pdfs: list[dict[str, Any]],
) -> dict[str, Any]:
    """Αντιστοίχιση parsed PDF → work_log (κενά protocol_from/to μόνο)."""
    wls = _work_log_rows_for_day(employer_afm, branch_aa, day_iso)
    used: set[tuple[int, str]] = set()
    stats = {
        "matched_in": 0,
        "matched_out": 0,
        "updated": 0,
        "already_ok": 0,
        "empty_section": 0,
        "no_wl": 0,
        "ambiguous": 0,
        "conflict": 0,
        "details": [],
    }

    def _find(kind: str, row: dict[str, str]) -> list[dict[str, Any]]:
        target_afm = norm_afm(row.get("afm"))
        target_hm = _norm_hm(row.get("time"))
        out: list[dict[str, Any]] = []
        for w in wls:
            if norm_afm(w.get("employee_afm")) != target_afm:
                continue
            wl_hm = _norm_hm(w.get("hour_from") if kind == "in" else w.get("hour_to"))
            if wl_hm == target_hm:
                out.append(w)
        return out

    updates: list[tuple[str, str, int]] = []  # col, protocol, wl_id

    for pdf in parsed_pdfs:
        protocol = _norm_protocol(str(pdf.get("protocol") or ""))
        if not protocol:
            continue
        for kind, row, col in (
            ("in", pdf.get("in_row"), "protocol_from"),
            ("out", pdf.get("out_row"), "protocol_to"),
        ):
            if not row:
                stats["empty_section"] += 1
                continue
            matches = _find(kind, row)
            if not matches:
                stats["no_wl"] += 1
                stats["details"].append(
                    {
                        "protocol": protocol,
                        "kind": kind,
                        "status": "no_wl",
                        "afm": row.get("afm"),
                        "time": row.get("time"),
                    }
                )
                continue
            if len(matches) > 1:
                stats["ambiguous"] += 1
                continue
            w = matches[0]
            wl_id = int(w["id"])
            key = (wl_id, col)
            if key in used:
                stats["ambiguous"] += 1
                continue
            used.add(key)
            existing = str(w.get(col) or "").strip()
            if existing == protocol:
                stats["already_ok"] += 1
                if kind == "in":
                    stats["matched_in"] += 1
                else:
                    stats["matched_out"] += 1
                continue
            if existing:
                stats["conflict"] += 1
                continue
            updates.append((col, protocol, wl_id))
            if kind == "in":
                stats["matched_in"] += 1
            else:
                stats["matched_out"] += 1
            w[col] = protocol

    if updates:
        with cursor() as cur:
            for col, protocol, wl_id in updates:
                cur.execute(
                    f"""
                    UPDATE dbo.karta_work_log
                    SET {col} = ?
                    WHERE id = ?
                      AND ({col} IS NULL OR LTRIM(RTRIM({col})) = N'')
                    """,
                    (protocol, wl_id),
                )
                if cur.rowcount > 0:
                    stats["updated"] += 1

    return stats


def process_protocol_pdfs_for_day(
    *,
    session: requests.Session,
    portal_base: str,
    page_html: str,
    page_url: str,
    ctx: dict[str, Any],
    day: date,
    skip_download_existing: bool = True,
) -> dict[str, Any]:
    """Μία ημέρα: search → PDF → parse → match work_log + χρονόμετρα."""
    day_iso = day.isoformat()
    day_ergani = format_date_for_ergani(day_iso)
    employer = str(ctx.get("employer_afm") or "")
    branch = str(ctx.get("branch_aa") or "0").strip() or "0"
    out_dir = protocol_pdf_day_dir(employer, branch, day_iso)
    out_dir.mkdir(parents=True, exist_ok=True)

    t0 = time.perf_counter()
    result: dict[str, Any] = {
        "day": day_iso,
        "items": 0,
        "pages": 0,
        "pdf_ok": 0,
        "pdf_fail": 0,
        "pdf_skipped_existing": 0,
        "match_updated": 0,
        "match_in": 0,
        "match_out": 0,
        "match_no_wl": 0,
        "match_conflict": 0,
        "search_s": None,
        "pdf_s": None,
        "parse_match_s": None,
        "total_s": None,
        "error": "",
        "out_dir": str(out_dir),
    }

    try:
        t = time.perf_counter()
        items, pages = search_workcard_items_for_day(
            session, page_html, page_url, ctx, day_ergani
        )
        result["search_s"] = round(time.perf_counter() - t, 3)
        result["pages"] = pages
        result["items"] = len(items)
    except Exception as ex:
        result["error"] = f"search: {ex}"
        result["total_s"] = round(time.perf_counter() - t0, 3)
        return result

    t_pdf = time.perf_counter()
    pdf_paths: list[Path] = []
    for item in items:
        label = item.get("protocol") or item["portal_id"]
        path = out_dir / _safe_filename(f"{label}_{item['portal_id']}.pdf")
        try:
            if skip_download_existing and path.exists() and path.stat().st_size > 1000:
                result["pdf_skipped_existing"] += 1
                result["pdf_ok"] += 1
                pdf_paths.append(path)
                continue
            ok, skipped = _download_pdf(session, portal_base, item, path)
            if ok:
                result["pdf_ok"] += 1
                if skipped:
                    result["pdf_skipped_existing"] += 1
                pdf_paths.append(path)
            else:
                result["pdf_fail"] += 1
        except Exception:
            result["pdf_fail"] += 1
    result["pdf_s"] = round(time.perf_counter() - t_pdf, 3)

    t_m = time.perf_counter()
    parsed: list[dict[str, Any]] = []
    for path in pdf_paths:
        try:
            parsed.append(parse_protocol_pdf_file(path))
        except Exception:
            continue
    match = apply_pdf_content_matches(
        employer_afm=employer,
        branch_aa=branch,
        day_iso=day_iso,
        parsed_pdfs=parsed,
    )
    result["parse_match_s"] = round(time.perf_counter() - t_m, 3)
    result["match_updated"] = int(match.get("updated") or 0)
    result["match_in"] = int(match.get("matched_in") or 0)
    result["match_out"] = int(match.get("matched_out") or 0)
    result["match_no_wl"] = int(match.get("no_wl") or 0)
    result["match_conflict"] = int(match.get("conflict") or 0)
    result["total_s"] = round(time.perf_counter() - t0, 3)
    return result


def sync_protocol_pdf_match_from_portal(
    ctx: dict[str, Any],
    *,
    from_iso: str,
    to_iso: str,
    session: requests.Session | None = None,
    run_id: str | None = None,
    relogin_every: int = 20,
) -> dict[str, Any]:
    """Ημερήσιο loop: PDF δηλώσεων + αντιστοίχιση στην πραγματική."""
    log = logger_for_store("protocol_pdf_match", ctx, run_id=run_id)
    start = datetime.strptime(str(from_iso)[:10], "%Y-%m-%d").date()
    end = datetime.strptime(str(to_iso)[:10], "%Y-%m-%d").date()
    if start > end:
        start, end = end, start

    portal_base = _portal_base(ctx)
    own_session = session is None
    sess = session or _login_session(ctx)
    days: list[dict[str, Any]] = []
    t_all = time.perf_counter()
    day = start
    day_i = 0

    try:
        while day <= end:
            day_i += 1
            if day_i > 1 and (day_i - 1) % max(1, int(relogin_every)) == 0:
                try:
                    sess = _login_session(ctx)
                    log.info(f"Επανασύνδεση portal πριν από {day.isoformat()}")
                except Exception as ex:
                    log.warning(f"Αποτυχία επανασύνδεσης: {ex}")
            try:
                page_html, page_url = _open_work_card_search(sess, portal_base)
            except Exception as ex:
                row = {
                    "day": day.isoformat(),
                    "items": 0,
                    "pages": 0,
                    "pdf_ok": 0,
                    "pdf_fail": 0,
                    "pdf_skipped_existing": 0,
                    "match_updated": 0,
                    "match_in": 0,
                    "match_out": 0,
                    "match_no_wl": 0,
                    "match_conflict": 0,
                    "search_s": None,
                    "pdf_s": None,
                    "parse_match_s": None,
                    "total_s": None,
                    "error": f"open: {ex}",
                    "out_dir": "",
                }
                days.append(row)
                day += timedelta(days=1)
                continue

            row = process_protocol_pdfs_for_day(
                session=sess,
                portal_base=portal_base,
                page_html=page_html,
                page_url=page_url,
                ctx=ctx,
                day=day,
            )
            days.append(row)
            log.info(
                f"PDF match {row['day']}: items={row['items']} "
                f"pdf_ok={row['pdf_ok']} updated={row['match_updated']} "
                f"total={row['total_s']}s",
                **{k: v for k, v in row.items() if k != "out_dir"},
            )
            day += timedelta(days=1)
    finally:
        if own_session:
            try:
                sess.close()
            except Exception:
                pass

    wall = round(time.perf_counter() - t_all, 3)
    summary = {
        "success": all(not d.get("error") for d in days) and sum(d.get("pdf_fail") or 0 for d in days) == 0,
        "from": start.isoformat(),
        "to": end.isoformat(),
        "days_count": len(days),
        "items_total": sum(int(d.get("items") or 0) for d in days),
        "pdf_ok_total": sum(int(d.get("pdf_ok") or 0) for d in days),
        "pdf_fail_total": sum(int(d.get("pdf_fail") or 0) for d in days),
        "pdf_skipped_total": sum(int(d.get("pdf_skipped_existing") or 0) for d in days),
        "match_updated_total": sum(int(d.get("match_updated") or 0) for d in days),
        "match_in_total": sum(int(d.get("match_in") or 0) for d in days),
        "match_out_total": sum(int(d.get("match_out") or 0) for d in days),
        "match_no_wl_total": sum(int(d.get("match_no_wl") or 0) for d in days),
        "wall_seconds": wall,
        "days": days,
        "detail": (
            f"PDF match {start.isoformat()}–{end.isoformat()}: "
            f"{sum(int(d.get('pdf_ok') or 0) for d in days)} PDF, "
            f"{sum(int(d.get('match_updated') or 0) for d in days)} ενημερώσεις work_log"
        ),
    }
    return summary
