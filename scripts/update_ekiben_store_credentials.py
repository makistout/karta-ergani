"""Ενημέρωση διαπιστευτηρίων καταστήματος ΕΚΙΒΕΝ II (μία φορά)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import repo_store as repo

# Τιμές από περιβάλλον (μία φορά) — π.χ. ERGANI_PORTAL_USER / ERGANI_PORTAL_PASSWORD
import os

USERNAME = os.environ.get("EKIBEN_USERNAME", "EFKA41585730").strip()
PASSWORD = os.environ.get("EKIBEN_PASSWORD", "").strip()
USERTYPE = os.environ.get("EKIBEN_USERTYPE", "01").strip() or "01"
STORE_NAME_MATCH = "ΕΚΙΒΕΝ"  # EKIBEN II


def main() -> int:
    if not PASSWORD:
        print("Ορίστε EKIBEN_PASSWORD στο περιβάλλον.")
        return 1
    stores = repo.list_store_configs()
    matches = [
        s
        for s in stores
        if STORE_NAME_MATCH.upper() in (s.get("name") or "").upper()
        or "802788173" in str(s.get("employer_afm") or "")
    ]
    if not matches:
        print("Δεν βρέθηκε κατάστημα ΕΚΙΒΕΝ — δημιουργία νέας εγγραφής.")
        new_id = repo.save_store_credentials(
            name="ΕΚΙΒΕΝ II",
            username=USERNAME,
            password=PASSWORD,
            usertype=USERTYPE,
            ergani_env="production",
            employer_afm="802788173",
            branch_aa="0",
            store_id=None,
        )
        print(f"Δημιουργήθηκε id={new_id}")
        return 0

    for s in matches:
        sid = int(s["id"])
        repo.save_store_credentials(
            name=s.get("name") or "ΕΚΙΒΕΝ II",
            username=USERNAME,
            password=PASSWORD,
            usertype=USERTYPE,
            ergani_env=s.get("ergani_env") or "production",
            employer_afm=s.get("employer_afm") or "802788173",
            branch_aa=s.get("branch_aa") or "0",
            store_id=sid,
        )
        print(f"Ενημερώθηκε id={sid} name={s.get('name')!r} username={USERNAME} usertype={USERTYPE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
