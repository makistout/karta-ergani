# Ergani Portal Sync

## Στόχος

Οι portal sync ροές συμπληρώνουν όσα δεν επιστρέφονται εύκολα από τα Ergani API endpoints.

## Βασικά Modules

- `app/portal_schedule_sync.py`: ψηφιακό ωράριο.
- `app/portal_work_log_sync.py`: πραγματική απασχόληση.
- `app/portal_excel.py`: Excel export parsing.
- `app/portal_excel_archive.py`: αρχειοθέτηση Excel exports **τρέχουσας ημέρας** για debug.
- `app/portal_auth.py`, `app/portal_form_util.py`: login/forms helpers.

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
