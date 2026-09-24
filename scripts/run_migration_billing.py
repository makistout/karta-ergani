"""Δημιουργία πινάκων τιμολόγησης (νέοι πίνακες, χωρίς αλλαγή store)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.repo_billing import ensure_tables, list_plans, tables_available  # noqa: E402


def main() -> int:
    ensure_tables()
    print(f"billing tables ready={tables_available()} plans={len(list_plans(active_only=False))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
