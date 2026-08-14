# Decisions

## Changelog vs Living Docs

Το `CHANGELOG.md` κρατά ιστορικό αλλαγών. Η τρέχουσα τεχνική εικόνα μεταφέρεται στα `docs/*.md`.

## Compatibility Facades

Όταν μεγάλο module χωρίζεται, το αρχικό filename μπορεί να παραμένει ως facade που κάνει import/re-export τις public functions. Αυτό μειώνει το ρίσκο σε routes/tests/scripts που ήδη εισάγουν το παλιό module.

## Empty Work Log Sync

Κενή πραγματική απασχόληση από portal δεν είναι απαραίτητα σφάλμα. Η εφαρμογή το αντιμετωπίζει ως επιτυχημένο sync με `count=0` όταν δεν υπάρχουν πραγματικές καταγραφές.

## Employment Contract Snapshots

Τα στοιχεία σύμβασης από Μητρώα Ergani αποθηκεύονται σε **`karta_employment_contract`** ως append-only ιστορικό ανά `(employer_afm, branch_aa, employee_afm)`.

- Κάθε γραμμή φέρει υποχρεωτικά ΑΦΜ εργοδότη + παράρτημα + ΑΦΜ εργαζομένου.
- Νέα έκδοση μόνο όταν αλλάζει το `content_hash` (tracked πεδία) ή η ημ. ενημέρωσης Ergani.
- Πηγή: portal `Mitroa/ErgazomenosSearch.aspx` → `Ergazomenos.aspx` (όχι EX_BASE_05).
- **Scope sync:** ενεργοί στο κατάστημα ∩ ΑΦΜ στο τοπικό `karta_schedule` (όχι ολόκληρο το Μητρώο παραρτήματος).
- UI: `/ui/employees/detail` (ανά εργαζόμενο) και `/ui/employees/contracts` (λίστα)· προβολή με `employees.view`, sync με `employees.sync`.
- Το `flex_arrival_minutes` συγχρονίζεται και στο `karta_employee`.

## Notification Links

Τα Telegram/Email recipient links πρέπει να είναι public absolute URLs. Τα redirects μετά από PIN πρέπει να είναι relative paths ώστε να μένουν στο ίδιο host.

## Frontend Strategy

Το shared UI shell ανήκει σε templates. Το page-specific behavior μένει σε ξεχωριστό JS ανά σελίδα. Κοινά browser helpers μπαίνουν σε μικρά shared JS modules και εκτίθενται μέσω του global `Office` για συμβατότητα.

## WRKCardSE Aitiologia

Η Ergani απαιτεί ή απαγορεύει τον κωδικό καθυστέρησης ανάλογα με το αν το χτύπημα είναι εντός ή εκτός επιτρεπόμενου ορίου. Η εφαρμογή **δεν** αφήνει το frontend να στέλνει πάντα `001` ούτε να βασίζεται μόνο σε retry από την απάντηση Ergani.

Κανόνας:

- `reference_date < σήμερα` ή `> σήμερα` → `001`
- `reference_date == σήμερα` → έλεγχος ώρας χτυπήματος έναντι ψηφιακού ωραρίου και `flex_arrival_minutes`
- Η υλοποίηση είναι κοινή για live punch, προγενέστερη από UI και retro-hit από Telegram (`work_card_payload.py`, `routes_work_card.py`).

## Ergani Protocol 1-1 Matching

Τα πρωτόκολλα χτυπημάτων από portal Ergani (WorkCardSearch) αποθηκεύονται στο `karta_ergani_protocol`.
Η σύνδεση με την πραγματική γίνεται **μόνο** όταν υπάρχει βέβαιη 1-1 αντιστοίχιση:

- κλειδί: `(store_id, ημερολογιακή ημέρα, HH:MM)` από `submit_at` ↔ `hour_from` / `hour_to`,
- overnight έξοδος: `hour_to` σε επόμενη ημερολογιακή ημέρα όταν `hour_to < hour_from`,
- αν στην ίδια στιγμή υπάρχουν **>1 πρωτόκολλα** ή **>1** γραμμές πραγματικής → **κενό**
  (δεν επιλέγουμε «το πρώτο» ή με ΑΦΜ — το portal δεν δίνει εργαζόμενο στο πρωτόκολλο).

Αποτέλεσμα: `karta_work_log.protocol_from` / `protocol_to` (κύρια αποθήκευση) και, όπου
υπάρχει δική μας δήλωση, συμπλήρωση `karta_declaration.protocol`.

## Canonical Public Homepage

Για SEO και branded traffic, το marketing landing είναι στο **root** (`/`), όχι σε slug path.

- Canonical: `https://erganios.gr/`
- Legacy slug `/psifiaki-karta-ergasias/` → **301** στο `/`
- Δεν υπάρχουν δύο ενεργές σελίδες με ίδιο περιεχόμενο
- Το `/` είναι public path (χωρίς login) και το frontend δεν πρέπει να φορτώνει office APIs στο homepage (`office-boot.js`, `office-auth.js`)

## WRKCardSE Correction Flow

Όταν υπάρχει ήδη ίδια δήλωση κάρτας για εργαζόμενο / ημέρα / τύπο, το σύστημα δεν σταματά σε τυφλό error. Η προτιμώμενη ροή είναι:

- πρώτο submit,
- αν υπάρξει duplicate, επιστροφή `correction_available`,
- ρητή επιβεβαίωση από τον χρήστη,
- δεύτερο submit σε `correction_mode`,
- αντικατάσταση της παλιάς τοπικής εγγραφής από τη νέα επιτυχημένη διορθωτική.

Η διόρθωση δεν πρέπει να ξεκινά αυτόματα χωρίς confirm, γιατί αλλάζει το ενεργό χτύπημα που προβάλλει το erganiOS.

## Work Log Display Rule

Σε περίπτωση πολλαπλών δηλώσεων κάρτας για ίδια ημέρα/τύπο, το `/ui/work-log` πρέπει να προβάλλει το **τελευταίο χτύπημα** ως ενεργό και να επισημαίνει ότι αποτελεί διόρθωση προηγούμενης ώρας.

## Exit Needs Correction Notification

Όταν υπάρχει έξοδος πριν από την είσοδο (λάθος σειρά χτυπημάτων), το σύστημα δεν πρέπει να
προτείνει διόρθωση με βάση την ώρα λήξης του ψηφιακού προγράμματος ούτε το λάθος χτύπημα.

Κανόνας ενεργοποίησης (ίδιος με `late_check_out`):

- **αναμενόμενη έξοδος** = πραγματική είσοδος + (τέλος ψηφ. ωραρίου − αρχή ψηφ. ωραρίου)
- ειδοποίηση `exit_needs_correction` όταν περάσουν ≥15′ από την αναμενόμενη έξοδο
- η προτεινόμενη διορθωτική έξοδος στο Telegram/Email/UI είναι η ίδια αναμενόμενη ώρα

Η Αρχική αναφορά εμφανίζει ξεχωριστό πλαίσιο για αυτή την περίπτωση, ώστε να ξεχωρίζει από
τις υπόλοιπες καμπάνες.

## Weekly Schedule Excel Import

Η μαζική ενημέρωση εβδομαδιαίου ωραρίου γίνεται με **2 βήματα**:

1. Ανέβασμα `.xlsx` template → αποθήκευση σε staging (`karta_schedule_import_*`) και προεπισκόπηση diff.
2. Επιβεβαίωση χρήστη → WTODaily ανά αλλαγή (όχι άμεση εγγραφή στο `karta_schedule` χωρίς Ergani).

Κανόνες ανάγνωσης γραμμής Excel:

- `Ενέργεια = ΡΕΠΟ` → ημέρα ανάπαυσης (ΑΝ), οι ώρες αγνοούνται.
- Κενή ενέργεια + συμπληρωμένες ώρες → αλλαγή ωραρίου (ΕΡΓ, σπαστό με Από2/Έως2).
- Κενή ενέργεια + κενές ώρες → `skip` (δεν αλλάζει τίποτα).
- **Δεν υπάρχει καθόλου στο φύλλο της ημέρας** → `absent` (ΡΕΠΟ / χωρίς εργασία).

Κατέβασμα Excel template από `/ui/schedule` (τρέχουσα ή επόμενη εβδομάδα) μέσω
`GET /api/schedule/import/template?week=current|next`. Κενό template (εργαζόμενοι +
ημερομηνίες· χωρίς προγεμισμένες ώρες/ΡΕΠΟ από `karta_schedule`).

Μετά την επιβεβαίωση εισαγωγής τρέχει portal sync για το εύρος ημερομηνιών του αρχείου.
Οι αλλαγές καταγράφονται στο audit (`excel_import` + καρτέλα «Αλλαγές ωραρίου»).

Η προεπισκόπηση δείχνει **τρέχον** vs **νέο** από το τοπικό `karta_schedule` (μετά sync).
