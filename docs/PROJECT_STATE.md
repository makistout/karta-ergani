# Project State

Τρέχουσα εικόνα της εφαρμογής `karta-ergani`.

## Σκοπός

Η εφαρμογή εξυπηρετεί λογιστικό/διαχειριστικό γραφείο για ψηφιακή κάρτα εργασίας:

- διαχείριση καταστημάτων και Ergani credentials,
- συγχρονισμό εργαζομένων, ψηφιακού ωραρίου, πραγματικής απασχόλησης και μηνιαίας κατάστασης,
- αναφορά ελλείψεων κάρτας,
- υποβολή χτυπήματος κάρτας, WTODaily, WTOWeek και leave,
- Telegram/Email ειδοποιήσεις με PIN και δημόσιους συνδέσμους.

## Κύριες Ροές

- `/ui/`: αρχική αναφορά κατάστασης κάρτας.
- `/ui/stores`: καταστήματα και επιλογή ενεργού καταστήματος.
- `/ui/stores/credentials`: Ergani API/portal credentials.
- `/ui/stores/notify`: λήπτες Telegram/Email.
- `/ui/employees`: εργαζόμενοι και εβδομαδιαίο πρόγραμμα.
- `/ui/schedule`: ψηφιακό ωράριο.
- `/ui/work-log`: πραγματική απασχόληση.
- `/ui/missing-cards`: ελλιπή χτυπήματα.
- `/ui/work-card`: υποβολή ψηφιακής κάρτας.
- `/ui/sync`: χειροκίνητος συγχρονισμός.
- `/ui/sync-log`: καταγραφές συγχρονισμών και audit σε δύο tabs.

## Τρέχουσες Προτεραιότητες Συντήρησης

- Κρατάμε το `CHANGELOG.md` ως ιστορικό, όχι ως μοναδική τεκμηρίωση.
- Κρατάμε μικρά modules με σαφή ρόλο: routes για HTTP, repos για SQL, services για business logic.
- Frontend shell, CSS και κοινό JS χωρίζονται ώστε αλλαγές navigation/UI να μην απαιτούν αλλαγές σε πολλά αρχεία.
- Τα παλιά μεγάλα Python modules μένουν ως compatibility facades όπου χρειάζεται, ώστε τα υπάρχοντα imports να μη σπάσουν απότομα.

## Τρέχουσα Δομή UI

- Οι office σελίδες είναι Jinja templates στο `app/templates/ui/`.
- Το κοινό layout είναι το `app/templates/ui/base.html`.
- Το sidebar είναι partial στο `app/templates/ui/partials/_sidebar.html`.
- Τα παλιά static HTML αρχεία στο `app/static/ui/` καταργήθηκαν.
- Το shared CSS φορτώνεται από `app/static/css/office.css` ως manifest με επιμέρους αρχεία
  foundation/components/sync/forms/report/work-card/responsive.
- Το shared JS φορτώνεται από μικρά `office-*.js` modules:
  chrome, store, feedback, table, sync, format, store-sync, work-log, auth, boot.

## Responsive Συμπεριφορά

- Σε tablet/mobile το sidebar δεν γίνεται οριζόντια λωρίδα. Γίνεται hamburger menu και
  ανοίγει με click.
- Οι πίνακες `table.data` δεν κρατούν mobile `min-width`. Το `office-table.js` βάζει
  labels στα cells και το `office-responsive.css` τους μετατρέπει σε card layout.
- Οι βασικές λίστες (`sync-log`, `employees`, `schedule`, `work-log`, `missing-cards`,
  `work-card`, `stores`) πρέπει να αποφεύγουν οριζόντιο scroll σε mobile/tablet.

## Πρόσφατα UI Fixes

- `/ui/employees`: αφαιρέθηκε η «Μηνιαία» στήλη μέχρι να υπάρχουν δεδομένα, προστέθηκε
  ξεχωριστό action για εβδομαδιαίο πρόγραμμα και βελτιώθηκε το εικονίδιο ιστορικού
  πραγματικής απασχόλησης.
- `/ui/stores/notify`: το πεδίο καταστήματος ανοίγει πάντα όλα τα καταστήματα με
  click/focus, ακόμη και μετά από πολλαπλές επιλογές.
- `/ui/sync-log`: το tab **Συγχρονισμός** δείχνει όλες τις καταγραφές by default και
  φιλτράρει με autocomplete καταστήματος. Το tab **Ενέργειες ειδοποιήσεων** δείχνει
  `today-hit` / `today-action` audit events με στήλη **Ποιος** όπου υπάρχει λήπτης token.
- `/ui/sync-log`: το tab **Απεσταλμένες ειδοποιήσεις** δείχνει τις post-sync αποστολές
  Telegram/Email ανά κατάστημα, λήπτη, εργαζόμενο, κανάλι και τύπο ειδοποίησης.
- `/ui/sync-log`: η αναζήτηση στο tab **Συγχρονισμός** ψάχνει και μέσα στις γραμμές
  `karta_sync_log`, συμπεριλαμβανομένων structured fields από αποστολές ειδοποιήσεων.

## Κανόνες Ειδοποιήσεων

- Τα PIN ληπτών είναι μοναδικά ανά κατάστημα.
- Η εφαρμογή ελέγχει διπλό PIN στο UI και στο backend save ληπτών.
- Το migration `sql/alter_unique_notify_pin_per_store.sql` προσθέτει unique filtered index
  στη βάση, αφού πρώτα ελέγξει για υπάρχοντα διπλότυπα.
- Κάθε λήπτης έχει πολιτική επανάληψης στη σελίδα `/ui/stores/notify`:
  - `Μία φορά και αυτόματο snooze`: μετά από επιτυχή post-sync αποστολή γράφεται
    `karta_today_notify_snooze`, άρα η υπάρχουσα ροή δεν ξαναστέλνει την ίδια περίπτωση.
  - `Συνέχεια κάθε 15 λεπτά μέχρι ενέργεια`: δεν γράφεται snooze μετά την αποστολή,
    οπότε η ειδοποίηση επανέρχεται στα επόμενα scheduled post-sync μέχρι snooze ή άλλη ενέργεια.
- Οι αυτόματες post-sync ειδοποιήσεις γράφουν γραμμή sync log ανά κανάλι/λήπτη/εργαζόμενο
  με `event=today_notification_send`, `recipient_*`, `employee_*`, `notify_kind` και
  `notification_channel`, **και snapshot βάσης** (`work_log_hour_from/to`, `card_check_in/out`,
  `work_log_synced_at`) τη στιγμή της αποστολής — βλ. `notify_db_snapshot()`.
- Το post-sync notification worker χρησιμοποιεί το ήδη φορτωμένο schedule του card report
  και γράφει progress/step logs ανά εργαζόμενο/λήπτη, ώστε να μη γίνεται δεύτερο schedule
  lookup ανά ειδοποίηση και να φαίνεται ακριβώς πού καθυστερεί ένα κατάστημα.
