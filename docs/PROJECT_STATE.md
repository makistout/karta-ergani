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

- `/`: δημόσια marketing landing (canonical SEO homepage).
- `/psifiaki-karta-ergasias/`: 301 redirect προς `/`.
- `/ui/`: αρχική αναφορά κατάστασης κάρτας (μετά από login).
- `/ui/stores`: καταστήματα και επιλογή ενεργού καταστήματος.
- `/ui/stores/credentials`: Ergani API/portal credentials.
- `/ui/stores/notify`: λήπτες Telegram/Email.
- `/ui/employees`: εργαζόμενοι και εβδομαδιαίο πρόγραμμα.
- `/ui/schedule`: ψηφιακό ωράριο (quick dates: Χθες, Σήμερα, Αύριο, Μεθαύριο).
- `/ui/work-log`: πραγματική απασχόληση (quick dates: Χθες, Σήμερα, Αύριο, Μεθαύριο).
- `/ui/missing-cards`: ελλιπή χτυπήματα.
- `/ui/work-card`: υποβολή ψηφιακής κάρτας.
- `/ui/sync`: χειροκίνητος συγχρονισμός.
- `/ui/sync-log`: καταγραφές συγχρονισμών και audit σε δύο tabs.

## Public Landing

- Το canonical public URL είναι **`https://erganios.gr/`**. Το `/psifiaki-karta-ergasias/` κάνει **301 redirect** εκεί. Το `/ui/landing` κάνει επίσης 301 στο `/`.
- Η σελίδα είναι διαθέσιμη χωρίς office login και παρουσιάζει τις βασικές ροές ωραρίου, WTODaily,
  WTOWeek, ειδοποιήσεις και αποκλίσεις.
- SEO title: «Εφαρμογή Ψηφιακής Κάρτας Εργασίας | erganiOS». H1: «Η Ψηφιακή Κάρτα Εργασίας σε τάξη, κάθε μέρα».
- Public nav: κουμπί **Login** → `/ui/login`.
- Το `office-boot.js` / `office-auth.js` δεν φορτώνουν office chrome ούτε κάνουν login redirect στο `/` και στα SEO slugs.
- Προστέθηκαν **5 SEO υποσελίδες** (informational guides) μέσω `app/landing_seo.py`:
  `/psifiaki-karta-logistika-grafeia/`, `/ti-einai-i-psifiaki-karta-ergasias/`,
  `/chttypimata-kartas-ergasias/`, `/apokliseis-psifiakis-kartas/`, `/psifiako-orario-ergani/`.
- Κοινά partials: `_landing_public_nav.html`, `_landing_public_footer.html`· base άρθρου `landing-article.html`.
- Το public περιεχόμενο δεν προβάλλει audit/καταγραφές ως feature και αποφεύγει αναφορές
  σε ιστορικό κινήσεων εργαζομένων.
- Ο τιμοκατάλογος οργανώνεται σε εύρη εργαζομένων **2-5**, **6-15**, **16-30**, **30+**.
- Η φόρμα επικοινωνίας υποβάλλει στο `/api/contact` (`app/routes_contact.py`), κάνει validation
  και honeypot, και στέλνει email μέσω **SMTP Mailgun** (`app/email_notify.py`, `SMTP_*` στο `.env`).
- **Παραλήπτης:** `info@erganios.gr` (`CONTACT_TO_EMAIL`). **Αποστολέας:** `SMTP_FROM_EMAIL` /
  `SMTP_FROM_NAME` (π.χ. `noreply@erganios.gr`). Το email του επισκέπτη μπαίνει στο σώμα του μηνύματος.
- Το slideshow χρησιμοποιεί ανωνυμοποιημένα screenshots: θολωμένα ονόματα, ΑΦΜ,
  στοιχεία εργοδότη/καταστήματος και φόντο πίσω από modal όπου εμφανίζονται προσωπικά
  ή αναγνωριστικά στοιχεία.
- Τα public screenshot filenames είναι ουδέτερα, χωρίς όνομα πραγματικού καταστήματος.
- SEO: canonical, meta tags, Open Graph, JSON-LD. Logo `erganios-logo.png` με διαφανές φόντο.
- Τα μικρά uppercase labels του landing γράφονται άτονα στο template, ώστε να αποδίδονται
  καθαρά όταν εφαρμόζεται `text-transform: uppercase`.

## Disclaimer Ψηφιακής Κάρτας

- Κόκκινο box «**Τι απαγορεύεται**» με απαγορεύσεις χρήσης κάρτας και disclaimer ευθύνης **erganiOS**.
- Εμφανίζεται στη **Ψηφιακή κάρτα** (`/ui/work-card`) και στο **Κλείστε όλα**
  (`/ui/missing-cards/close-all`).
- Κοινό partial: `app/templates/ui/partials/_work_card_disclaimer.html`· CSS στο `office-work-card.css`.

## Ψηφιακή Κάρτα (WRKCardSE)

- Υποβολή live και προγενέστερης καταχώρησης από `/ui/work-card` και `/ui/retro-hit` (Telegram link).
- **Αιτιολογία καθυστέρησης** (`f_aitiologia`): αποφασίζεται στο backend πριν την αποστολή στην Ergani.
  - Ημερομηνία **≠ σήμερα** → πάντα κωδικός `001`.
  - **Σήμερα** → αιτιολογία μόνο αν η ώρα χτυπήματος είναι εκτός ψηφιακού ωραρίου ± ευελιξία
    (`flex_arrival_minutes`, default 15′). Εντός ορίου δεν στέλνεται πεδίο αιτιολογίας.
- **Διορθωτικό χτύπημα**: όταν η Ergani ή η τοπική βάση δηλώνει ότι υπάρχει ήδη ίδια είσοδος/έξοδος για την ημέρα,
  το backend επιστρέφει πρόταση διόρθωσης και το UI ζητά επιβεβαίωση από τον χρήστη. Με επιβεβαίωση,
  γίνεται retry σε `correction_mode` και η νέα επιτυχημένη υποβολή αντικαθιστά την παλιά τοπική εγγραφή του ίδιου τύπου.
- Κατά portal sync στη σελίδα κάρτας κλειδώνουν τα κουμπιά εισόδου/εξόδου μέχρι να ολοκληρωθεί το sync.
- Το `office-sync.js` poll-άρει σωστά το status URL μετά από `work-card-sync`.

## Πραγματική Απασχόληση (`/ui/work-log`)

- Όταν υπάρχει νεότερη διορθωτική δήλωση κάρτας για την ίδια ημέρα/τύπο, το UI δείχνει το **τελευταίο χτύπημα**.
- Αν υπάρχει προηγούμενο που αντικαταστάθηκε, εμφανίζεται badge `διορθ.` με tooltip που αναφέρει την προηγούμενη ώρα.

## Excel Template Εβδομαδιαίου Ωραρίου

- Λογική template: `app/schedule_excel_template.py` · script `scripts/make_weekly_template.py`.
- Στο `/ui/schedule`:
  - **Κατέβασμα Excel** (τρέχουσα / επόμενη εβδομάδα) → κενό `.xlsx` με οδηγίες και όλους τους εργαζόμενους.
  - **Ανέβασμα Excel** (ανέβασμα → προεπισκόπηση → επιβεβαίωση):
  - ενδιάμεσοι πίνακες `karta_schedule_import_batch` / `karta_schedule_import_row`,
  - σύγκριση τρέχοντος ψηφ. ωραρίου με τις τιμές του Excel,
  - εφαρμογή μόνο για γραμμές `new` / `update` μέσω WTODaily στο Ergani,
  - **μετά την επιβεβαίωση** συγχρονισμός portal για το διάστημα του αρχείου.
- Κανόνες γραμμής:
  - `ΡΕΠΟ` = ρεπό · κενή ενέργεια + ώρες = αλλαγή · κενό παντού = skip.
  - **Λείπει εντελώς από το φύλλο ημέρας** = χωρίς εργασία (ΡΕΠΟ, `absent`).
- Καταγραφές: audit `wto_daily.schedule_change` (πηγή `excel_import`) + `schedule_import.batch_applied` · προβολή στο `/ui/sync-log#schedule`.
- Το template υποστηρίζει:
  - ένα φύλλο ανά ημέρα,
  - πραγματική ημερομηνία σε κάθε tab,
  - όλους τους εργαζόμενους σε γραμμές,
  - `Ενέργεια` μόνο `ΡΕΠΟ` ή κενό,
  - ώρες `Από1/Έως1/Από2/Έως2` με validation μορφής `ΩΩ:ΛΛ`.

## Αρχική Αναφορά

- Ο date picker της Αρχικής δείχνει μόνο **Χθες / Σήμερα / Αύριο / Μεθαύριο**.
- Τα quick buttons της Αρχικής κάνουν άμεσο load της αναφοράς. Το κουμπί **Ανανέωση**
  παραμένει για χειροκίνητο refresh ή αλλαγές από τα πεδία ημερομηνίας.
- Πριν από την έναρξη του ψηφιακού ωραρίου, και εφόσον δεν υπάρχει πραγματική απασχόληση ή
  χτύπημα κάρτας, η γραμμή εμφανίζει και **Αλλαγή ωραρίου** και **Ρεπό/Άδεια**.
- Τα κουμπιά **Ρεπό** και **Άδεια** εμφανίζονται μόνο **πριν την έναρξη** του ωραρίου κάθε
  εργαζομένου (`leave_eligible` / `canDeclareRestBeforeShift`), όχι με σταθερή ώρα.
- Για ημέρες **ρεπό / μη εργασίας** τα actions **Ρεπό** και **Αλλαγή ωραρίου** παραμένουν
  πάντα διαθέσιμα (`rest_day_actions_always`), σήμερα και σε μελλοντικές ημέρες.
- Για μελλοντικές ημέρες τα actions βασίζονται στο καταχωρημένο ψηφιακό ωράριο που έχει
  συγχρονιστεί για την ημέρα.
- Η αλλαγή ωραρίου WTODaily από την Αρχική υποστηρίζει σπαστό ωράριο με πολλαπλά
  διαστήματα. Το payload στέλνει πολλαπλά `ErgazomenosWTOAnalytics`, το τοπικό
  `karta_schedule` κρατά όλες τις γραμμές της ημέρας και η Αρχική τις εμφανίζει ενιαία
  (`09:00 – 13:00 / 17:00 – 21:00`).
- Οι καμπάνες για σπαστό ωράριο είναι ανά διάστημα: π.χ. `late_check_in@09:00` και
  `late_check_in@17:00`. Έτσι auto-send/snooze του πρωινού δεν μπλοκάρει το απογευματινό.
- Οι επιτυχημένες WTODaily αλλαγές ωραρίου γράφουν ειδικό audit event
  `wto_daily.schedule_change` με παλιό/νέο ωράριο, εργαζόμενο, ημερομηνία, protocol και
  actor/office user. Το γενικό mutating-request audit παραμένει συμπληρωματικό.
- Οι WTODaily αποστολές χρησιμοποιούν κοινό helper με αυτόματο refresh/retry του Ergani
  bearer όταν επιστρέφει `Authorization has been denied`, για manual αλλαγές από Αρχική
  και αλλαγές από ροές ειδοποίησης.
- Οι δηλώσεις `WRKCardSE` χειρίζονται και το ειδικό case όπου ο Ergani πρώτα απορρίπτει
  το `f_aitiologia` ως μη επιτρεπτό και μετά απαιτεί το στοιχείο στο XSD: γίνεται retry
  με `f_aitiologia: null`.

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

### Κανόνες καμπάνας (τρέχουσα ημέρα)

Grace **15 λεπτά** (`NOTIFY_GRACE_MINUTES`) για είσοδο και έξοδο.

| `notify_kind` | Πότε ενεργοποιείται |
|---------------|---------------------|
| `late_check_in` | Ψηφ. ωράριο εργασίας, χωρίς είσοδο, ≥15' από **αρχή ωραρίου**. Μία φορά/ημέρα (auto). |
| `late_check_out` | Είσοδος χωρίς έξοδο, με ψηφ. ωράριο: **αναμενόμενη έξοδος = είσοδος + (τέλος−αρχή ωραρίου)** · alert ≥15' μετά (συμπ. μετά μεσάνυχτα). |
| `exit_needs_correction` | Έξοδος **πριν** από την είσοδο (λάθος χτύπημα). Ίδιος υπολογισμός αναμενόμενης εξόδου με `late_check_out` · alert ≥15' μετά · προτείνεται διορθωτική έξοδος. |
| `missing_exit_8h` | **Μόνο χωρίς** ψηφ. ωράριο εργασίας (ρεπό/«—»): ≥8h από είσοδο χωρίς έξοδο. |
| `exit_without_entry` | Έξοδος χωρίς είσοδο. |

- **Ώρες για κανόνες**: `merge_notify_work_hours()` — κάρτα υπερισχύει πραγματικής.
- **Ακύρωση**: `card_event_blocks_today_notify()` αν υπάρχει αντίστοιχο χτύπημα στη βάση erganiOS.
- **Κείμενο alert**: ώρες ψηφ. ωραρίου + (για έξοδο) είσοδος/αναμενόμενη έξοδος — `format_today_alert_notification`.
- Στην **Αρχική** αναφορά, για `exit_needs_correction` εμφανίζεται ξεχωριστό πλαίσιο διόρθωσης
  με την προτεινόμενη ώρα `είσοδος + διάρκεια ωραρίου` (όχι `schedule.hour_to`).

### Debug Excel portal (σήμερα)

Κάθε sync ωραρίου/πραγματικής που αφορά **την τρέχουσα ημέρα** αποθηκεύει το raw Excel export
στο `data/portal_excel_debug/` για διερεύνηση διαφορών portal ανά 15 λεπτά. Βλ. `ERGANI_PORTAL_SYNC.md`.

## Scheduled Sync

- Το βασικό scheduled sync (`scheduled_today_sync`) κρατά σημερινό ψηφιακό ωράριο και
  σημερινή πραγματική απασχόληση.
- Η ξεχωριστή operation `scheduled_future_schedule_sync` τρέχει μία φορά την ημέρα ανά
  κατάστημα, μετά την ώρα αυτόματου κλεισίματος προηγούμενης ημέρας (default `00:30`).
- Η future phase συγχρονίζει μόνο ψηφιακό ωράριο για αύριο και μεθαύριο, ώστε η Αρχική να
  έχει διαθέσιμα στοιχεία για αλλαγή ωραρίου/ρεπό πριν χρειαστεί χειροκίνητο sync.
