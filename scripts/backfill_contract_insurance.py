"""Γέμισμα κύριας/επικουρικής ασφάλισης στις τρέχουσες συμβάσεις από EX_BASE_05."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.ergani_env import store_api_context  # noqa: E402
from app.repo_employment_contract import refresh_personal_from_ex_base_05  # noqa: E402
from app.repo_store import list_store_configs  # noqa: E402


def main() -> int:
    stores = list_store_configs()
    inserted = 0
    scanned = 0
    errors = 0
    skipped = 0
    for store in stores:
        if not str(store.get("web_username") or "").strip():
            skipped += 1
            continue
        ctx = store_api_context(store)
        result = refresh_personal_from_ex_base_05(ctx)
        name = store.get("name") or store.get("id")
        if not result.get("success"):
            errors += 1
            print(f"FAIL {name}: {result.get('detail')}")
            continue
        scanned += int(result.get("scanned") or 0)
        inserted += int(result.get("inserted") or 0)
        print(
            f"OK {name}: {result.get('inserted') or 0} νέες εκδόσεις "
            f"({result.get('scanned') or 0} εργαζόμενοι)"
        )
    print(
        f"Σύνολο: {inserted} νέες εκδόσεις, {scanned} εργαζόμενοι, "
        f"{errors} σφάλματα, {skipped} χωρίς web user"
    )
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
