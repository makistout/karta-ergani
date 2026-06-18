"""Διαγραφή operational δεδομένων ενός καταστήματος — κρατάει karta_store_config (+ notify recipients)."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import repo_store
from app.db import get_connection


def purge_store_data(store_id: int, *, dry_run: bool = False) -> int:
    cfg = repo_store.get_store_config(store_id)
    if not cfg:
        print(f"Δεν βρέθηκε κατάστημα id={store_id}")
        return 1

    afm = str(cfg["employer_afm"]).strip()
    branch = str(cfg.get("branch_aa") or "0").strip()
    name = cfg.get("name") or ""

    print(f"Κατάστημα id={store_id} name={name!r} AFM={afm} branch_aa={branch}")
    if dry_run:
        print("(dry-run — χωρίς διαγραφές)")

    conn = get_connection()
    cur = conn.cursor()
    try:
        steps: list[tuple[str, str, tuple]] = []

        # card events (πριν declarations αν χρειαστεί — εδώ μόνο branch)
        steps.append(
            (
                "karta_card_event",
                """
                DELETE FROM dbo.karta_card_event
                WHERE f_afm_ergodoti = ? AND f_aa = ?
                """,
                (afm, branch),
            )
        )

        steps.append(
            (
                "karta_schedule",
                """
                DELETE FROM dbo.karta_schedule
                WHERE employer_afm = ? AND branch_aa = ?
                """,
                (afm, branch),
            )
        )

        steps.append(
            (
                "karta_work_log",
                """
                DELETE FROM dbo.karta_work_log
                WHERE employer_afm = ? AND branch_aa = ?
                """,
                (afm, branch),
            )
        )

        steps.append(
            (
                "karta_employment",
                """
                DELETE e FROM dbo.karta_employment e
                INNER JOIN dbo.karta_employer em ON em.id = e.employer_id
                INNER JOIN dbo.karta_parartima p ON p.id = e.parartima_id
                WHERE em.afm = ? AND p.code_aa = ?
                """,
                (afm, branch),
            )
        )

        steps.append(
            (
                "karta_employee (orphans)",
                """
                DELETE FROM dbo.karta_employee
                WHERE id NOT IN (SELECT employee_id FROM dbo.karta_employment)
                """,
                (),
            )
        )

        steps.append(
            (
                "karta_parartima",
                """
                DELETE p FROM dbo.karta_parartima p
                INNER JOIN dbo.karta_employer em ON em.id = p.employer_id
                WHERE em.afm = ? AND p.code_aa = ?
                """,
                (afm, branch),
            )
        )

        steps.append(
            (
                "karta_telegram_punch_token",
                "DELETE FROM dbo.karta_telegram_punch_token WHERE store_id = ?",
                (store_id,),
            )
        )

        steps.append(
            (
                "karta_sync_log",
                """
                DELETE l FROM dbo.karta_sync_log l
                INNER JOIN dbo.karta_sync_run r ON r.run_id = l.run_id
                WHERE r.store_id = ?
                """,
                (store_id,),
            )
        )

        steps.append(
            (
                "karta_sync_run",
                "DELETE FROM dbo.karta_sync_run WHERE store_id = ?",
                (store_id,),
            )
        )

        if not dry_run:
            for label, sql, params in steps:
                cur.execute(sql, params)
                n = cur.rowcount
                print(f"  {label}: {n} rows deleted")

            cur.execute(
                """
                UPDATE dbo.karta_store_config
                SET last_sync_at = NULL,
                    schedule_last_sync_at = NULL,
                    work_log_last_sync_at = NULL,
                    updated_at = SYSDATETIMEOFFSET()
                WHERE id = ?
                """,
                (store_id,),
            )
            print(f"  karta_store_config: reset sync timestamps (id={store_id})")
            conn.commit()
        else:
            for label, sql, params in steps[:-2]:
                if "orphans" in label:
                    cur.execute(
                        "SELECT COUNT(*) FROM dbo.karta_employee WHERE id NOT IN (SELECT employee_id FROM dbo.karta_employment)"
                    )
                else:
                    cur.execute(sql.replace("DELETE", "SELECT COUNT(*) FROM", 1).split("FROM", 1)[0] + "SELECT COUNT(*) FROM" + sql.split("FROM", 1)[1].split("WHERE")[0] if False else "")
            print("  (dry-run skipped counts)")

        # verify
        checks = [
            ("schedule", "SELECT COUNT(*) FROM dbo.karta_schedule WHERE employer_afm=? AND branch_aa=?", (afm, branch)),
            ("work_log", "SELECT COUNT(*) FROM dbo.karta_work_log WHERE employer_afm=? AND branch_aa=?", (afm, branch)),
            ("employment", """SELECT COUNT(*) FROM dbo.karta_employment e
                JOIN dbo.karta_employer em ON em.id=e.employer_id
                JOIN dbo.karta_parartima p ON p.id=e.parartima_id
                WHERE em.afm=? AND p.code_aa=?""", (afm, branch)),
            ("store_config", "SELECT COUNT(*) FROM dbo.karta_store_config WHERE id=?", (store_id,)),
        ]
        print("\nΜετά την ενέργεια:")
        for label, sql, params in checks:
            cur.execute(sql, params)
            print(f"  {label}: {cur.fetchone()[0]}")

        print("\nOK — διατηρήθηκε η εγγραφή καταστήματος (credentials, κατάλογοι).")
        return 0
    except Exception as ex:
        conn.rollback()
        print(f"ERROR: {ex}", file=sys.stderr)
        return 1
    finally:
        cur.close()
        conn.close()


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("store_id", type=int, nargs="?", default=6)
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()
    return purge_store_data(args.store_id, dry_run=args.dry_run)


if __name__ == "__main__":
    raise SystemExit(main())
