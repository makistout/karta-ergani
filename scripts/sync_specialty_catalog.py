"""Κατέβασμα καταλόγου ειδικοτήτων ΣΤΕΠ'92 από Ergani στον τοπικό πίνακα."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.repo_specialty_catalog import ensure_table  # noqa: E402
from app.specialty_catalog_sync import (  # noqa: E402
    run_specialty_catalog_sync_scheduled,
    sync_specialty_catalog,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync Ergani Step92 specialties locally")
    parser.add_argument("--force-scheduled", action="store_true", help="Γράψε και sync log ως scheduled")
    args = parser.parse_args()
    ensure_table()
    if args.force_scheduled:
        result = run_specialty_catalog_sync_scheduled(force=True)
    else:
        result = sync_specialty_catalog()
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0 if result.get("success") or (result.get("specialty_catalog") or {}).get("success") else 1


if __name__ == "__main__":
    raise SystemExit(main())
