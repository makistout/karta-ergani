"""CLI για περιοδικό συγχρονισμό — καλείται από Windows Task Scheduler κάθε 15 λεπτά."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config import Config  # noqa: E402


def compile_app_sources(app_dir: Path | None = None) -> list[str]:
    """Συλλέγει SyntaxError/IndentationError στα app/*.py χωρίς να φορτώσει routes."""
    errors: list[str] = []
    folder = app_dir or (ROOT / "app")
    for path in sorted(folder.glob("*.py")):
        try:
            compile(path.read_text(encoding="utf-8"), str(path), "exec")
        except SyntaxError as exc:
            errors.append(f"{path.name}:{exc.lineno}: {exc.msg}")
    return errors


def _record_source_guard(message: str) -> None:
    try:
        import uuid

        from app import repo_sync_log

        if not repo_sync_log.tables_available():
            return
        run_id = str(uuid.uuid4())
        repo_sync_log.create_run(run_id, operation="scheduled_sync_source_guard", store_id=None)
        repo_sync_log.finish_run(
            run_id,
            status="error",
            message=message[:500],
            result={"success": False, "error": message},
        )
    except Exception:
        pass


def _import_scheduled_sync():
    from app.scheduled_sync import run_scheduled_sync

    return run_scheduled_sync


def _env_flag(name: str, *, default: bool = True) -> bool:
    import os

    raw = os.environ.get(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in ("1", "true", "yes", "on")


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Συγχρονισμός όλων των καταστημάτων: "
            "σημερινό ψηφιακό ωράριο/πραγματική και ημερήσια φάση "
            "μελλοντικού ψηφιακού ωραρίου."
        )
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Εμφάνιση καταστημάτων χωρίς sync",
    )
    parser.add_argument(
        "--store-id",
        type=int,
        action="append",
        dest="store_ids",
        help="Μόνο συγκεκριμένο κατάστημα (επαναλήψιμο)",
    )
    parser.add_argument(
        "--date",
        dest="work_date",
        help=(
            "ISO ημερομηνία βάσης (προεπιλογή σήμερα), π.χ. 2026-06-17. "
            "Η πραγματική και το βασικό ωράριο συγχρονίζονται για αυτή την ημέρα."
        ),
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Τρέξε ακόμα κι αν τρέχει ήδη scheduled sync",
    )
    args = parser.parse_args()

    if not _env_flag("KARTA_SCHEDULED_SYNC_ENABLED", default=True):
        print("KARTA_SCHEDULED_SYNC_ENABLED=0 — παράλειψη.")
        return 0

    try:
        Config.validate_for_startup()
    except RuntimeError as ex:
        print(f"ΣΦΑΛΜΑ ρυθμίσεων: {ex}", file=sys.stderr)
        return 1

    syntax_errors = compile_app_sources()
    if syntax_errors:
        guard_msg = "SyntaxError σε app/: " + "; ".join(syntax_errors[:8])
        print(guard_msg, file=sys.stderr)
        _record_source_guard(guard_msg)

    try:
        run_scheduled_sync = _import_scheduled_sync()
    except Exception as ex:
        fail = f"Αποτυχία φόρτωσης scheduled sync: {ex}"
        print(fail, file=sys.stderr)
        _record_source_guard(fail)
        return 1

    result = run_scheduled_sync(
        store_ids=args.store_ids,
        work_date_iso=args.work_date,
        dry_run=args.dry_run,
        skip_if_running=not args.force,
    )

    if result.get("skipped"):
        print(result.get("reason") or "Παράλειψη — ήδη τρέχει.")
        return 0

    if result.get("dry_run"):
        print(result.get("message") or f"Dry-run: {result.get('count', 0)} καταστήματα")
        for name in result.get("stores") or []:
            print(f"  - {name}")
        return 0

    print(result.get("message") or "Ολοκληρώθηκε.")
    for row in result.get("stores") or []:
        mark = "OK" if row.get("success") else "FAIL"
        print(f"  [{mark}] {row.get('store_name')} — {row.get('detail')}")

    return 0 if result.get("success") else 1


if __name__ == "__main__":
    raise SystemExit(main())
