"""Αρχειοθέτηση Excel exports portal (τρέχουσα ημέρα) για debug."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any

from app.work_card_payload import tz_athens
from config import Config


def _parse_ergani_date(value: str) -> date | None:
    s = (value or "").strip()
    for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(s[:10] if fmt == "%Y-%m-%d" else s, fmt).date()
        except ValueError:
            continue
    return None


def range_includes_today(date_from: str, date_to: str, *, now: datetime | None = None) -> bool:
    """True όταν το εύρος αναζήτησης portal περιλαμβάνει τη σημερινή ημέρα (Europe/Athens)."""
    today = (now or datetime.now(tz_athens())).date()
    start = _parse_ergani_date(date_from)
    end = _parse_ergani_date(date_to or date_from)
    if start is None:
        return False
    if end is None:
        end = start
    if end < start:
        start, end = end, start
    return start <= today <= end


def _excel_extension(content_type: str, content: bytes) -> str:
    ctype = (content_type or "").lower()
    head = content[:8]
    if head.startswith(b"\xd0\xcf\x11\xe0") or "ms-excel" in ctype:
        return ".xls"
    return ".xlsx"


def _safe_token(value: str, *, max_len: int = 32) -> str:
    s = re.sub(r"[^\w\-]+", "_", (value or "").strip())
    return (s[:max_len] or "na").strip("_")


@dataclass
class PortalExcelArchive:
    """Γράφει raw Excel + metadata για sync τρέχουσας ημέρας."""

    kind: str  # work_log | schedule
    store_id: int | None
    store_name: str | None
    employer_afm: str
    branch_aa: str
    date_from: str
    date_to: str
    run_id: str | None = None
    _saved_path: Path | None = field(default=None, init=False, repr=False)

    @property
    def saved_path(self) -> Path | None:
        return self._saved_path

    @classmethod
    def for_sync(
        cls,
        *,
        kind: str,
        ctx: dict[str, Any],
        date_from: str,
        date_to: str,
        run_id: str | None = None,
    ) -> PortalExcelArchive | None:
        if not Config.KARTA_PORTAL_EXCEL_DEBUG_TODAY:
            return None
        if not range_includes_today(date_from, date_to):
            return None
        return cls(
            kind=(kind or "").strip() or "unknown",
            store_id=int(ctx["id"]) if ctx.get("id") is not None else None,
            store_name=str(ctx.get("name") or "") or None,
            employer_afm=str(ctx.get("employer_afm") or "").strip(),
            branch_aa=str(ctx.get("branch_aa") or "0").strip() or "0",
            date_from=(date_from or "").strip(),
            date_to=(date_to or date_from or "").strip(),
            run_id=(run_id or "").strip() or None,
        )

    def _base_dir(self) -> Path:
        root = Config.PORTAL_EXCEL_DEBUG_DIR
        today_iso = datetime.now(tz_athens()).strftime("%Y-%m-%d")
        sid = self.store_id if self.store_id is not None else "unknown"
        return root / f"store_{sid}" / today_iso

    def _stem(self) -> str:
        now = datetime.now(tz_athens())
        run_part = _safe_token((self.run_id or "manual")[:8], max_len=8)
        return (
            f"{_safe_token(self.kind, max_len=16)}_"
            f"{now.strftime('%H%M%S')}_{run_part}"
        )

    def _write_meta(self, path: Path, payload: dict[str, Any]) -> None:
        meta_path = path.with_suffix(path.suffix + ".meta.json")
        meta_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _purge_old_days(self, keep_dir: Path) -> None:
        store_dir = keep_dir.parent
        if not store_dir.is_dir():
            return
        for child in store_dir.iterdir():
            if not child.is_dir() or child == keep_dir:
                continue
            try:
                for f in child.iterdir():
                    f.unlink(missing_ok=True)
                child.rmdir()
            except OSError:
                continue

    def record_excel(
        self,
        content: bytes,
        content_type: str,
        *,
        row_count: int,
        fetch_source: str = "excel",
    ) -> Path | None:
        if not content:
            return self.record_failure("Κενό αρχείο Excel export", fetch_source=fetch_source)
        base = self._base_dir()
        base.mkdir(parents=True, exist_ok=True)
        self._purge_old_days(base)
        ext = _excel_extension(content_type, content)
        path = base / f"{self._stem()}{ext}"
        path.write_bytes(content)
        meta = {
            "kind": self.kind,
            "saved_at": datetime.now(tz_athens()).isoformat(timespec="seconds"),
            "store_id": self.store_id,
            "store_name": self.store_name,
            "employer_afm": self.employer_afm,
            "branch_aa": self.branch_aa,
            "date_from": self.date_from,
            "date_to": self.date_to,
            "run_id": self.run_id,
            "fetch_source": fetch_source,
            "row_count": int(row_count),
            "content_type": content_type,
            "bytes": len(content),
            "excel_path": str(path),
        }
        self._write_meta(path, meta)
        self._saved_path = path
        return path

    def record_failure(
        self,
        error: str,
        *,
        fetch_source: str = "excel",
        html_row_count: int | None = None,
    ) -> Path | None:
        base = self._base_dir()
        base.mkdir(parents=True, exist_ok=True)
        self._purge_old_days(base)
        path = base / f"{self._stem()}.meta.json"
        meta = {
            "kind": self.kind,
            "saved_at": datetime.now(tz_athens()).isoformat(timespec="seconds"),
            "store_id": self.store_id,
            "store_name": self.store_name,
            "employer_afm": self.employer_afm,
            "branch_aa": self.branch_aa,
            "date_from": self.date_from,
            "date_to": self.date_to,
            "run_id": self.run_id,
            "fetch_source": fetch_source,
            "error": (error or "").strip(),
            "html_row_count": html_row_count,
            "excel_path": None,
        }
        path.write_text(
            json.dumps(meta, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        self._saved_path = path
        return path

    def record_fallback(
        self,
        *,
        excel_error: str | None,
        html_row_count: int,
        fetch_source: str,
    ) -> Path | None:
        return self.record_failure(
            excel_error or "Excel export απέτυχε — χρήση HTML grid",
            fetch_source=fetch_source,
            html_row_count=html_row_count,
        )


def log_excel_archive_saved(archive: PortalExcelArchive | None, log: Any | None) -> None:
    if archive is None or log is None:
        return
    path = archive.saved_path
    if not path:
        return
    writer = getattr(log, "info", None)
    if writer:
        writer(
            f"Debug Excel τρέχουσας ημέρας: {path}",
            portal_excel_debug=str(path),
        )
