"""Snapshot τρεχόντων ΑΦΜ Μητρώου ανά κατάστημα — ανίχνευση νέων προσλήψεων."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

_SNAPSHOT_DIRNAME = "mitroo_afm_snapshots"
_AFM_RE = re.compile(r"^\d{9}$")


def _norm_afm(value: Any) -> str:
    digits = re.sub(r"\D", "", str(value or ""))[:9]
    return digits if _AFM_RE.fullmatch(digits) else ""


def _snapshot_dir() -> Path:
    path = Path(__file__).resolve().parents[1] / "data" / _SNAPSHOT_DIRNAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def _snapshot_path(employer_afm: str, branch_aa: str) -> Path:
    ea = _norm_afm(employer_afm) or "unknown"
    aa = str(branch_aa or "0").strip()[:32] or "0"
    safe_aa = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in aa)
    return _snapshot_dir() / f"{ea}_{safe_aa}.json"


def load_mitroo_afm_snapshot(employer_afm: str, branch_aa: str) -> set[str] | None:
    """Επιστρέφει προηγούμενο σύνολο ΑΦΜ ή None αν δεν υπάρχει ακόμα snapshot."""
    path = _snapshot_path(employer_afm, branch_aa)
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, UnicodeError):
        return None
    if isinstance(raw, dict):
        values = raw.get("afms") or []
    elif isinstance(raw, list):
        values = raw
    else:
        return None
    out: set[str] = set()
    for value in values:
        afm = _norm_afm(value)
        if afm:
            out.add(afm)
    return out


def save_mitroo_afm_snapshot(
    employer_afm: str,
    branch_aa: str,
    afms: set[str] | list[str],
) -> None:
    path = _snapshot_path(employer_afm, branch_aa)
    cleaned = sorted({_norm_afm(a) for a in afms if _norm_afm(a)})
    payload: dict[str, Any] = {
        "employer_afm": _norm_afm(employer_afm),
        "branch_aa": str(branch_aa or "0").strip()[:32] or "0",
        "count": len(cleaned),
        "afms": cleaned,
    }
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=0),
        encoding="utf-8",
    )
