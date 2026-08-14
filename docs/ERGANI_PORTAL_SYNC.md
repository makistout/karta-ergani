# Ergani Portal Sync

## Στόχος

Οι portal sync ροές συμπληρώνουν όσα δεν επιστρέφονται εύκολα από τα Ergani API endpoints.

## Βασικά Modules

- `app/portal_schedule_sync.py`: ψηφιακό ωράριο.
- `app/portal_work_log_sync.py`: πραγματική απασχόληση.
- `app/portal_card_protocol_sync.py`: πρωτόκολλα χτυπημάτων κάρτας (WorkCardSearch Excel).
- `app/repo_ergani_protocol.py`: persist / upsert στο `karta_ergani_protocol`.
- `app/protocol_deduction_match.py`: 1-1 απαγωγή πρωτοκόλλων → `karta_work_log.protocol_from/to`
  (+ κενά `karta_declaration.protocol` όταν υπάρχει δική μας δήλωση).
- `app/portal_employment_contract_sync.py`: στοιχεία σύμβασης από Μητρώα
  (`Mitroa/ErgazomenosSearch.aspx` → `Ergazomenos.aspx`).
- `app/portal_excel.py`: Excel export parsing.
- `app/portal_excel_archive.py`: αρχειοθέτηση Excel exports **τρέχουσας ημέρας** για debug.
- `app/portal_auth.py`, `app/portal_form_util.py`: login/forms helpers.

## Στοιχεία Σύμβασης (Μητρώα)

- Persist σε `karta_employment_contract` (append-only snapshots).
- Scope: ενεργοί εργαζόμενοι ∩ ΑΦΜ στο `karta_schedule` του καταστήματος.
- Ημερήσιο scheduled: `scheduled_employment_contract_sync` (default `04:00`,
  `KARTA_SCHEDULED_EMPLOYMENT_CONTRACT_*`).
- Migration: `sql/alter_add_karta_employment_contract.sql` /
  `python scripts/ensure_karta_employment_contract_table.py`.

## Πρωτόκολλα Χτυπημάτων (WorkCardSearch)

- Persist σε `karta_ergani_protocol` (κατάλογος πρωτοκόλλων Ergani, ανεξάρτητα από δικές μας
  υποβολές WRKCardSE).
- Στήλη `protocol_last_sync_at` στο `karta_store_config`.
- **1-1 απαγωγή** (`apply_protocol_sync`): πρώτα τα δικά μας πρωτόκολλα στο
  `protocol_from`/`protocol_to`· μετά, αν `(store, ημέρα, HH:MM)` έχει **ακριβώς ένα**
  αχρησιμοποίητο πρωτόκολλο και **ακριβώς μία** κενή ώρα πραγματικής, τη γεμίζει.
  Δύο χτυπήματα την ίδια ώρα εκ των οποίων ένα δικό μας → το άλλο παίρνει το εναπομείναν.
- **Συγχρονισμός:**
  - αρχικός store sync (βήμα 6, 31 ημέρες),
  - περιοδικός `period_sync`,
  - νυχτερινός `scheduled_nightly_protocol_sync` (~03:00, χθες, μετά 30ήμερο πραγματικής).
- **Backfill:** `scripts/backfill_ergani_protocols.py`, `scripts/backfill_protocol_deduction_matches.py`.
- **Migrations:** `sql/alter_add_karta_ergani_protocol.sql`, `sql/alter_add_work_log_protocol.sql`,
  runners `ensure_karta_ergani_protocol_table.py`, `ensure_work_log_protocol_columns.py`.
- **Ρύθμιση:** `KARTA_SCHEDULED_PROTOCOL_SYNC_ENABLED`, `KARTA_SCHEDULED_PROTOCOL_SYNC_TIME`.

## Pattern

1. Φόρτωση store config και Ergani environment.
2. Login στο portal.
3. Άνοιγμα κατάλληλης σελίδας.
4. Υποβολή αναζήτησης.
5. Προτίμηση Excel export όπου υπάρχει.
6. Fallback σε grid parsing/pagination.
7. Persist rows στη βάση.
8. Καταγραφή αποτελέσματος σε sync log.

## Κενά Αποτελέσματα

Για πραγματική απασχόληση, κενή απάντηση portal μπορεί να είναι επιτυχής κατάσταση:

- `success=true`,
- `count=0`,
- χωρίς blocking error,
- ώστε να συνεχίζονται post-sync notifications.

## Refactor Note

Τα schedule/work-log portal modules έχουν κοινό ASP.NET form/grid parsing pattern. Κοινά helpers πρέπει να βγουν μόνο όταν δεν κρύβουν σημαντικές διαφορές ανά portal σελίδα.

## Debug Excel τρέχουσας ημέρας

Για διερεύνηση «γιατί το portal έδωσε 0 γραμμές στις 11:15 και 2 στις 11:30», κάθε sync
ωραρίου ή πραγματικής που **περιλαμβάνει σήμερα** αποθηκεύει:

- το raw αρχείο `.xlsx`/`.xls` από το portal export,
- αρχείο `.meta.json` (store, run_id, `row_count`, `fetch_source`, ημερομηνίες αναζήτησης).

**Τοποθεσία:** `data/portal_excel_debug/store_{id}/{YYYY-MM-DD}/` (δεν μπαίνει στο git).

**Ρυθμίσεις (.env):**

| Μεταβλητή | Προεπιλογή |
|-----------|------------|
| `KARTA_PORTAL_EXCEL_DEBUG_TODAY` | `true` |
| `KARTA_PORTAL_EXCEL_DEBUG_DIR` | `data/portal_excel_debug` |

**Logs:** μήνυμα `Debug Excel τρέχουσας ημέρας: …` στο sync run. Κρατά μόνο τη **σημερινή**
ημέρα ανά κατάστημα (διαγραφή παλαιότερων φακέλων αυτόματα).
