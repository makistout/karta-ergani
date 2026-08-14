"""Ανάλυση βέβαιων 1-1 αντιστοιχίσεων πρωτοκόλλων ↔ χτυπημάτων."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.protocol_deduction_match import analyze_one_to_one_matches  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Μέτρηση μοναδικών 1-1 αντιστοιχίσεων πρωτοκόλλων Ergani με χτυπήματα"
    )
    parser.add_argument("--from", dest="from_iso", help="YYYY-MM-DD")
    parser.add_argument("--to", dest="to_iso", help="YYYY-MM-DD")
    parser.add_argument("--json", action="store_true", help="Έξοδος JSON")
    args = parser.parse_args()

    result = analyze_one_to_one_matches(from_iso=args.from_iso, to_iso=args.to_iso)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(
            f"Διάστημα: {result['from_iso']} – {result['to_iso']}\n"
            f"1-1 πραγματική ↔ πρωτόκολλο (σύνολο): {result['total_work_log_matches']}\n"
            f"Εφαρμόσιμες ενημερώσεις χτυπημάτων: {result['total_card_updates']}\n"
            f"Καταστήματα: {result['stores_with_matches']}"
        )
        for row in result["per_store"]:
            print(
                f"  [{row['store_id']}] {row['store_name']}: "
                f"πραγματική={row['work_log_matches']}, "
                f"χτυπήματα={row['card_updates']}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
