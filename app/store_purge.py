"""Πλήρης διαγραφή επιχειρησιακών δεδομένων καταστήματος (ΑΦΜ + παράρτημα + αρχεία)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from app.db import cursor
from app.work_card_payload import norm_afm
from config import Config


def _norm_branch(value: str | None) -> str:
    return str(value or "0").strip() or "0"


def other_store_owns_branch(employer_afm: str, branch_aa: str, *, except_store_id: int | None = None) -> bool:
    afm = norm_afm(employer_afm)
    aa = _norm_branch(branch_aa)
    with cursor(commit=False) as cur:
        if except_store_id is None:
            cur.execute(
                """
                SELECT TOP 1 id FROM dbo.karta_store_config
                WHERE employer_afm = ?
                  AND LTRIM(RTRIM(ISNULL(branch_aa, N'0'))) = ?
                """,
                (afm, aa),
            )
        else:
            cur.execute(
                """
                SELECT TOP 1 id FROM dbo.karta_store_config
                WHERE employer_afm = ?
                  AND LTRIM(RTRIM(ISNULL(branch_aa, N'0'))) = ?
                  AND id <> ?
                """,
                (afm, aa, int(except_store_id)),
            )
        return cur.fetchone() is not None


def purge_employer_branch_files(
    employer_afm: str,
    branch_aa: str,
    *,
    store_id: int | None = None,
) -> dict[str, Any]:
    """Σβήνει PDF πρωτοκόλλων και σχετικά debug αρχεία για ΑΦΜ/παράρτημα."""
    afm = norm_afm(employer_afm)
    aa = _norm_branch(branch_aa)
    stats = {
        "protocol_pdf_dir_removed": False,
        "protocol_pdfs": 0,
        "excel_debug": 0,
        "excel_debug_store_dir_removed": False,
    }

    pdf_dir = Path(Config.PROTOCOL_PDF_DIR) / afm / aa
    if pdf_dir.is_dir():
        stats["protocol_pdfs"] = sum(1 for _ in pdf_dir.rglob("*.pdf"))
        shutil.rmtree(pdf_dir, ignore_errors=True)
        stats["protocol_pdf_dir_removed"] = True
        afm_root = pdf_dir.parent
        try:
            if afm_root.is_dir() and not any(afm_root.iterdir()):
                afm_root.rmdir()
        except OSError:
            pass

    debug_root = Path(Config.PORTAL_EXCEL_DEBUG_DIR)
    removed = 0
    if debug_root.is_dir():
        # κύρια δομή: portal_excel_debug/store_{id}/...
        if store_id is not None:
            store_dir = debug_root / f"store_{int(store_id)}"
            if store_dir.is_dir():
                removed += sum(1 for p in store_dir.rglob("*") if p.is_file())
                shutil.rmtree(store_dir, ignore_errors=True)
                stats["excel_debug_store_dir_removed"] = True
        for path in list(debug_root.rglob("*")):
            if not path.is_file():
                continue
            name = path.name
            rel = str(path.relative_to(debug_root)).replace("\\", "/")
            hit = False
            try:
                meta = json.loads(path.read_text(encoding="utf-8")) if name.endswith(".meta.json") else None
            except Exception:
                meta = None
            if isinstance(meta, dict):
                m_afm = norm_afm(str(meta.get("employer_afm") or meta.get("afm") or ""))
                m_aa = _norm_branch(str(meta.get("branch_aa") or meta.get("aa") or ""))
                if m_afm == afm and m_aa == aa:
                    hit = True
            if afm in name or afm in rel:
                if f"_{aa}_" in name or name.endswith(f"_{aa}") or f"-{aa}-" in name or f"/{aa}/" in f"/{rel}/":
                    hit = True
            if not hit:
                continue
            try:
                path.unlink(missing_ok=True)
                removed += 1
            except OSError:
                pass
    stats["excel_debug"] = removed
    return stats


def purge_employer_branch_data(
    employer_afm: str,
    branch_aa: str,
    *,
    purge_files: bool = True,
    store_id: int | None = None,
) -> dict[str, Any]:
    """Διαγράφει γραμμές ΒΔ με κλειδί ΑΦΜ+παράρτημα (όχι μόνο store_id CASCADE)."""
    afm = norm_afm(employer_afm)
    aa = _norm_branch(branch_aa)
    counts: dict[str, int] = {}

    statements = [
        ("karta_work_log", "DELETE FROM dbo.karta_work_log WHERE employer_afm=? AND LTRIM(RTRIM(ISNULL(branch_aa,N'0')))=?"),
        ("karta_schedule", "DELETE FROM dbo.karta_schedule WHERE employer_afm=? AND LTRIM(RTRIM(ISNULL(branch_aa,N'0')))=?"),
        ("karta_ergani_protocol", "DELETE FROM dbo.karta_ergani_protocol WHERE employer_afm=? AND LTRIM(RTRIM(ISNULL(branch_aa,N'0')))=?"),
        ("karta_monthly_status", "DELETE FROM dbo.karta_monthly_status WHERE employer_afm=? AND LTRIM(RTRIM(ISNULL(branch_aa,N'0')))=?"),
        ("karta_employment_contract", "DELETE FROM dbo.karta_employment_contract WHERE employer_afm=? AND LTRIM(RTRIM(ISNULL(branch_aa,N'0')))=?"),
        ("karta_portal_schedule_archive", "DELETE FROM dbo.karta_portal_schedule_archive WHERE employer_afm=? AND LTRIM(RTRIM(ISNULL(branch_aa,N'0')))=?"),
        ("karta_schedule_import_batch", "DELETE FROM dbo.karta_schedule_import_batch WHERE employer_afm=? AND LTRIM(RTRIM(ISNULL(branch_aa,N'0')))=?"),
        ("karta_audit_log", "DELETE FROM dbo.karta_audit_log WHERE employer_afm=? AND LTRIM(RTRIM(ISNULL(branch_aa,N'0')))=?"),
        ("karta_card_event", "DELETE FROM dbo.karta_card_event WHERE f_afm_ergodoti=? AND LTRIM(RTRIM(ISNULL(f_aa,N'0')))=?"),
        ("karta_declaration", "DELETE FROM dbo.karta_declaration WHERE employer_afm=?"),
    ]

    with cursor() as cur:
        for name, sql in statements:
            try:
                if name == "karta_declaration":
                    # δηλώσεις συχνά χωρίς branch — σβήνουμε μόνο αν δεν υπάρχει άλλο store του ΑΦΜ
                    cur.execute(
                        "SELECT COUNT(*) FROM dbo.karta_store_config WHERE employer_afm=?",
                        (afm,),
                    )
                    if int(cur.fetchone()[0] or 0) > 0:
                        counts[name] = 0
                        continue
                cur.execute(sql, (afm, aa) if name != "karta_declaration" else (afm,))
                counts[name] = int(cur.rowcount or 0)
            except Exception as ex:
                counts[name] = -1
                counts[f"{name}_error"] = str(ex)[:200]

        # απασχολήσεις στο συγκεκριμένο παράρτημα
        try:
            cur.execute("SELECT id FROM dbo.karta_employer WHERE afm=?", (afm,))
            erow = cur.fetchone()
            if erow:
                eid = int(erow[0])
                cur.execute(
                    """
                    SELECT id FROM dbo.karta_parartima
                    WHERE employer_id = ? AND LTRIM(RTRIM(ISNULL(code_aa, N'0'))) = ?
                    """,
                    (eid, aa),
                )
                par_ids = [int(r[0]) for r in cur.fetchall()]
                emp_del = 0
                par_del = 0
                for pid in par_ids:
                    cur.execute(
                        "DELETE FROM dbo.karta_employment WHERE employer_id=? AND parartima_id=?",
                        (eid, pid),
                    )
                    emp_del += int(cur.rowcount or 0)
                    # άδειο παράρτημα χωρίς άλλο store → διαγραφή εγγραφής παραρτήματος
                    cur.execute(
                        """
                        SELECT COUNT(*) FROM dbo.karta_store_config
                        WHERE employer_afm = ?
                          AND LTRIM(RTRIM(ISNULL(branch_aa, N'0'))) = ?
                        """,
                        (afm, aa),
                    )
                    if int(cur.fetchone()[0] or 0) == 0:
                        cur.execute(
                            "DELETE FROM dbo.karta_parartima WHERE id=? AND employer_id=?",
                            (pid, eid),
                        )
                        par_del += int(cur.rowcount or 0)
                counts["karta_employment"] = emp_del
                counts["karta_parartima"] = par_del
            else:
                counts["karta_employment"] = 0
                counts["karta_parartima"] = 0
        except Exception as ex:
            counts["karta_employment"] = -1
            counts["karta_employment_error"] = str(ex)[:200]

    file_stats: dict[str, Any] = {}
    if purge_files:
        file_stats = purge_employer_branch_files(afm, aa, store_id=store_id)

    return {"employer_afm": afm, "branch_aa": aa, "db": counts, "files": file_stats}


def delete_store_with_data(store_id: int) -> dict[str, Any]:
    """DELETE store_config (+ CASCADE) και purge ΑΦΜ+παραρτήματος αν δεν το κρατά άλλο store."""
    sid = int(store_id)
    with cursor(commit=False) as cur:
        cur.execute(
            """
            SELECT id, name, employer_afm, branch_aa
            FROM dbo.karta_store_config WHERE id = ?
            """,
            (sid,),
        )
        row = cur.fetchone()
        if not row:
            return {"success": False, "error": "Το κατάστημα δεν βρέθηκε"}
        cols = [d[0] for d in cur.description]
        store = dict(zip(cols, row))

    afm = str(store.get("employer_afm") or "").strip()
    aa = _norm_branch(store.get("branch_aa"))

    with cursor() as cur:
        cur.execute("DELETE FROM dbo.karta_store_config WHERE id = ?", (sid,))

    purge: dict[str, Any] | None = None
    if afm and not other_store_owns_branch(afm, aa):
        purge = purge_employer_branch_data(afm, aa, purge_files=True, store_id=sid)
    else:
        # άλλο store κρατά το branch (ή χωρίς ΑΦΜ): σβήνουμε μόνο excel debug του id
        files = {
            "protocol_pdf_dir_removed": False,
            "protocol_pdfs": 0,
            "excel_debug": 0,
            "excel_debug_store_dir_removed": False,
        }
        debug_root = Path(Config.PORTAL_EXCEL_DEBUG_DIR) / f"store_{sid}"
        if debug_root.is_dir():
            files["excel_debug"] = sum(1 for p in debug_root.rglob("*") if p.is_file())
            shutil.rmtree(debug_root, ignore_errors=True)
            files["excel_debug_store_dir_removed"] = True
        purge = {"employer_afm": afm, "branch_aa": aa, "db": {}, "files": files}

    return {
        "success": True,
        "store_id": sid,
        "name": store.get("name"),
        "employer_afm": afm,
        "branch_aa": aa,
        "purge": purge,
    }
