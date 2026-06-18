"""Εξαγωγή & parsing Excel από ASP.NET grid portal Ergani."""

from __future__ import annotations

import io
import re
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin

import requests

from app.portal_schedule_sync import REQUEST_TIMEOUT, _extract_aspnet_form_data

EXCEL_EXPORT_TIMEOUT = 300
EXCEL_EXPORT_ARGUMENT = "ExcelExport$1"


class _TableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.rows: list[list[str]] = []
        self._cur_row: list[str] | None = None
        self._cell_buf: list[str] = []
        self._in_cell = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        t = tag.lower()
        if t == "tr":
            self._cur_row = []
        elif t in ("td", "th") and self._cur_row is not None:
            self._in_cell = True
            self._cell_buf = []

    def handle_endtag(self, tag: str) -> None:
        t = tag.lower()
        if t in ("td", "th") and self._in_cell and self._cur_row is not None:
            text = re.sub(r"\s+", " ", "".join(self._cell_buf)).strip()
            self._cur_row.append(text)
            self._in_cell = False
            self._cell_buf = []
        elif t == "tr" and self._cur_row is not None:
            if any(c.strip() for c in self._cur_row):
                self.rows.append(self._cur_row)
            self._cur_row = None

    def handle_data(self, data: str) -> None:
        if self._in_cell:
            self._cell_buf.append(data)


def download_grid_excel(
    session: requests.Session,
    html: str,
    page_url: str,
    *,
    grid_event_target: str,
    excel_argument: str = EXCEL_EXPORT_ARGUMENT,
) -> tuple[bytes, str]:
    """POST __doPostBack ExcelExport — επιστρέφει (bytes, content-type)."""
    data = _extract_aspnet_form_data(html, include_text=True)
    data["__EVENTTARGET"] = grid_event_target
    data["__EVENTARGUMENT"] = excel_argument
    for key in list(data.keys()):
        if key.endswith("$SearchControlSearchButton"):
            del data[key]

    action = page_url
    m = re.search(r'<form[^>]+action="([^"]*)"', html, re.I)
    if m:
        action = urljoin(page_url, m.group(1))

    resp = session.post(
        action,
        data=data,
        timeout=EXCEL_EXPORT_TIMEOUT,
        allow_redirects=True,
    )
    if resp.status_code >= 400:
        raise RuntimeError(f"Αποτυχία Excel export — HTTP {resp.status_code}")
    if "error.aspx" in resp.url.lower():
        raise RuntimeError("Αποτυχία Excel export — error.aspx")
    ctype = (resp.headers.get("Content-Type") or "").split(";")[0].strip().lower()
    body = resp.content
    if not body:
        raise RuntimeError("Κενό αρχείο Excel export")
    if "text/html" in ctype and "DailyWorkTimesSearchControl" in resp.text[:4000]:
        if "MovableElement" not in resp.text and "<table" not in resp.text.lower():
            raise RuntimeError("Το Excel export επέστρεψε HTML σελίδα χωρίς πίνακα")
    return body, ctype


def _parse_xlsx(content: bytes) -> list[list[str]]:
    from openpyxl import load_workbook

    # read_only=False — το export Ergani έχει λανθασμένο dimension ref="A1"
    wb = load_workbook(io.BytesIO(content), read_only=False, data_only=True)
    try:
        ws = wb.active
        rows: list[list[str]] = []
        for row in ws.iter_rows(values_only=True):
            cells = ["" if v is None else str(v).strip() for v in row]
            if any(cells):
                rows.append(cells)
        return rows
    finally:
        wb.close()


def _parse_xls(content: bytes) -> list[list[str]]:
    import xlrd

    book = xlrd.open_workbook(file_contents=content)
    sheet = book.sheet_by_index(0)
    rows: list[list[str]] = []
    for r in range(sheet.nrows):
        cells = [str(sheet.cell_value(r, c)).strip() for c in range(sheet.ncols)]
        if any(cells):
            rows.append(cells)
    return rows


def _parse_html_table(content: bytes) -> list[list[str]]:
    text = content.decode("utf-8", errors="replace")
    parser = _TableParser()
    parser.feed(text)
    return parser.rows


def _header_index(headers: list[str], *needles: str) -> int | None:
    for i, h in enumerate(headers):
        norm = (h or "").upper().replace(" ", "")
        for n in needles:
            if n in norm:
                return i
    return None


def _work_log_row_from_cells(cells: list[str], col: dict[str, int]) -> list[str] | None:
    def pick(key: str, default: int) -> str:
        idx = col.get(key, default)
        return (cells[idx] if idx < len(cells) else "").strip()

    aa = pick("aa", 0)
    afm = re.sub(r"\D", "", pick("afm", 1))
    if not re.fullmatch(r"\d{8,11}", afm):
        return None
    eponymo = pick("eponymo", 2)
    onoma = pick("onoma", 3)
    work_date = pick("date", 4)
    hour_from = pick("from", 5)
    hour_to = pick("to", 6)
    return [aa, afm, eponymo, onoma, work_date, hour_from, hour_to]


def _detect_work_log_columns(header: list[str]) -> dict[str, int]:
    col: dict[str, int] = {}
    mapping = {
        "aa": ("ΑΑΠΑΡΑΡΤΗΜΑΤΟΣ", "ΑΑ", "AA"),
        "afm": ("ΑΦΜ", "AFM"),
        "eponymo": ("ΕΠΩΝΥΜΟ", "EPONIMO"),
        "onoma": ("ΟΝΟΜΑ", "ONOMA"),
        "date": ("ΗΜ/ΝΙΑ", "ΗΜΕΡΟΜΗΝΙΑ", "DATE"),
        "from": ("ΩΡΑΑΠΟ", "ΩΡΑΑΠΌ", "HOURFROM", "ΑΠΟ", "ΑΠΌ"),
        "to": ("ΩΡΑΕΩΣ", "HOURTO", "ΕΩΣ", "ΈΩΣ"),
    }
    for key, needles in mapping.items():
        idx = _header_index(header, *needles)
        if idx is not None:
            col[key] = idx
    return col


def normalize_work_log_grid_rows(raw_rows: list[list[str]]) -> list[list[str]]:
    """Μετατροπή γραμμών export → ίδια μορφή 7 κελιών με HTML grid."""
    if not raw_rows:
        return []

    header_row: list[str] | None = None
    col: dict[str, int] = {}
    start = 0
    for i, row in enumerate(raw_rows[:5]):
        if _header_index(row, "ΑΦΜ", "AFM") is not None:
            header_row = row
            col = _detect_work_log_columns(row)
            start = i + 1
            break

    if not col:
        col = {"aa": 0, "afm": 1, "eponymo": 2, "onoma": 3, "date": 4, "from": 5, "to": 6}

    out: list[list[str]] = []
    for row in raw_rows[start:]:
        if not row or all(not (c or "").strip() for c in row):
            continue
        if header_row and row == header_row:
            continue
        norm = _work_log_row_from_cells(row, col)
        if norm:
            out.append(norm)
    return out


def parse_work_log_export(content: bytes, content_type: str = "") -> list[list[str]]:
    """Parse Excel/HTML export πραγματικής απασχόλησης → grid rows."""
    ctype = (content_type or "").lower()
    head = content[:16]
    raw: list[list[str]] = []

    if head.startswith(b"PK") or "spreadsheetml" in ctype or "openxmlformats" in ctype:
        raw = _parse_xlsx(content)
    elif head.startswith(b"\xd0\xcf\x11\xe0") or "ms-excel" in ctype:
        try:
            raw = _parse_xls(content)
        except Exception:
            raw = _parse_html_table(content)
    elif b"<" in head or "html" in ctype:
        raw = _parse_html_table(content)
    else:
        for parser in (_parse_xlsx, _parse_xls, _parse_html_table):
            try:
                raw = parser(content)
                if raw:
                    break
            except Exception:
                continue

    return normalize_work_log_grid_rows(raw)


def fetch_work_log_rows_via_excel(
    session: requests.Session,
    html: str,
    page_url: str,
    *,
    grid_event_target: str,
) -> list[list[str]]:
    content, ctype = download_grid_excel(
        session, html, page_url, grid_event_target=grid_event_target
    )
    rows = parse_work_log_export(content, ctype)
    if not rows:
        raise RuntimeError("Το Excel export δεν περιέχει εγγραφές πραγματικής")
    return rows
