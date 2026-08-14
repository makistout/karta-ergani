"""Συμπλήρωση κενών πρωτοκόλλων χτυπημάτων από βέβαιες 1-1 αντιστοιχίσεις."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.protocol_deduction_match import apply_all_stores_one_to_one_matches  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="1-1 απαγωγή πρωτοκόλλων → karta_work_log + karta_declaration"
    )
    parser.add_argument("--from", dest="from_iso", help="YYYY-MM-DD")
    parser.add_argument("--to", dest="to_iso", help="YYYY-MM-DD")
    parser.add_argument("--store-id", type=int, action="append", dest="store_ids")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    result = apply_all_stores_one_to_one_matches(
        from_iso=args.from_iso,
        to_iso=args.to_iso,
        store_ids=args.store_ids,
    )
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(
            f"Διάστημα: {result.get('from_iso')} – {result['to_iso']}\n"
            f"Θέσεις 1-1: {result['matched']}\n"
            f"Ενημερώσεις: {result['updated']} "
            f"(πραγματική + δηλώσεις)"
        )
        for row in result.get("stores") or []:
            print(
                f"  [{row['store_id']}] {row['store_name']}: "
                f"updated={row['updated']} ({row.get('detail')})"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
