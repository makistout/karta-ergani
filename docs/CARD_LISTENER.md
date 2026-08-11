# Τοπικός listener ψηφιακής κάρτας

## Σκοπός και τρέχουσα κατάσταση

Ο listener είναι Windows client για υποβολές `WRKCardSE` από τη δημόσια IP της
επιχείρησης. Η λειτουργία είναι πρόσθετη, ρυθμίζεται ανά κατάστημα και δεν αφορά καμία
άλλη υπηρεσία ΕΡΓΑΝΗ.

Έχουν υλοποιηθεί schema, ρυθμίσεις, pairing, device isolation, listener API και Windows
listener v0.3.8. Ο dispatcher είναι συνδεδεμένος αποκλειστικά στη ροή `WRKCardSE`:
όταν το κατάστημα είναι σε mode `listener` και η συσκευή είναι online, δημιουργείται job και η
υποβολή γίνεται από τον listener. Όλες οι άλλες υπηρεσίες και τα καταστήματα σε mode `erganios`
συνεχίζουν από το υπάρχον erganiOS path.

Η ίδια επιλογή καναλιού εφαρμόζεται και στο προγραμματισμένο
`auto_close_prev_day`: το αυτόματο κλείσιμο παράγει `WRKCardSE` job στον online
listener του καταστήματος. Απευθείας υποβολή από erganiOS γίνεται μόνο όταν ο
listener είναι offline ή όταν το job παραμένει `queued` και ακυρωθεί atomically
για fallback. Αν ο listener έχει ήδη κάνει lease, δεν γίνεται δεύτερη υποβολή.

## Ρυθμίσεις καταστήματος

Στο `karta_store_config`:

- `card_submission_mode`: `erganios` ή `listener` (default `erganios`).
- `listener_offline_seconds`: default 60, επιτρεπτό 15–600.

Στις **Ρυθμίσεις → Listener ψηφιακής κάρτας** υπάρχουν αποθήκευση παραμέτρων, νέο
pairing, κατάσταση και ανάκληση. Επιτρέπεται ένας ενεργός listener ανά κατάστημα.
Η φόρμα χρησιμοποιεί συμπαγή διάταξη δύο στηλών σε desktop και μία στήλη σε μικρές
οθόνες, ώστε οι τίτλοι, οι μονάδες και τα πεδία να παραμένουν κοντά και ευανάγνωστα.

Αν η λίστα καταστημάτων δεν μπορεί να φορτωθεί, η οθόνη εμφανίζει σαφές μήνυμα
αποτυχίας server/βάσης αντί για το γενικό `Error: HTTP 500`. Το συγκεκριμένο μήνυμα
αφορά τη σύνδεση του erganiOS backend με τη βάση και όχι την επικοινωνία του listener.

Τα `datetimeoffset` πεδία που επιστρέφουν τα listener endpoints μετατρέπονται σε ISO
κείμενο μέσα στα SQL queries. Έτσι υποστηρίζονται και εγκαταστάσεις `pyodbc` που δεν
διαβάζουν απευθείας τον SQL Server τύπο `-155`.

Το νέο pairing γίνεται εξ ολοκλήρου μέσα στη φόρμα: συμπληρώνεται το αναγνωρίσιμο
όνομα υπολογιστή και επιλέγεται **Δημιουργία νέου pairing**. Μετά την επιτυχία
εμφανίζονται σε ξεχωριστά readonly πεδία το Device ID και το Device Token, με κουμπί
αντιγραφής. Το token εμφανίζεται μόνο τότε και καθαρίζεται όταν αλλάξει κατάστημα.
Η φόρμα είναι αρχικά κρυφή και ανοίγει από το κουμπί **Προσθήκη listener**, ώστε η
βασική οθόνη να παραμένει καθαρή όταν δεν γίνεται νέο pairing.

Το κουμπί **Αποθήκευση ρυθμίσεων** αποθηκεύει αποκλειστικά το
`card_submission_mode` και το `listener_offline_seconds`. Δεν δημιουργεί ούτε
ανανεώνει pairing.

Οι συνδεδεμένες συσκευές εμφανίζονται σε responsive πίνακα με κατάσταση, όνομα,
Device ID, δημόσια IP, έκδοση και τελευταία επικοινωνία. Η ημερομηνία προβάλλεται
στην τοπική ώρα του browser ως `ηη/μμ/εεεε ωω:λλ`. Το API επιστρέφει ήδη συλλογή
`devices`, ώστε η οθόνη να υποστηρίζει πολλαπλές γραμμές όταν επιτραπούν στο schema.
Κάθε Offline γραμμή έχει ενέργεια **Διαγραφή**. Το backend επανελέγχει ότι η συσκευή
είναι offline, διαγράφει οριστικά το pairing και επαναφέρει προληπτικά το κατάστημα σε
`card_submission_mode=erganios`. Online συσκευή δεν διαγράφεται.
Η **Ανάκληση** είναι ενέργεια ανά γραμμή και επιτρέπεται τόσο σε Online όσο και σε
Offline ενεργό listener. Ακυρώνει αμέσως μόνο το συγκεκριμένο Device ID/token και
επαναφέρει το κατάστημα σε `erganios`. Η ανακλημένη συσκευή παραμένει στον πίνακα ως
ιστορικό και μπορεί κατόπιν να διαγραφεί οριστικά.

## Απομόνωση και authentication

- Κάθε pairing δημιουργεί μοναδικά `device_id` και token για ένα `store_id`.
- Στον server αποθηκεύεται μόνο SHA-256 hash του token.
- Το καθαρό token εμφανίζεται μόνο κατά τη δημιουργία pairing.
- Το store προκύπτει server-side από την authenticated συσκευή και δεν επιλέγεται από
  τον listener.
- Τα listener endpoints βρίσκονται στο `/api/card-listener/v1/` και χρησιμοποιούν
  ανεξάρτητο device authentication.

## Βάση και migrations

- `karta_card_listener_device`: συσκευή, έκδοση, heartbeat και δημόσια IP.
- `karta_card_listener_job`: WRKCardSE job, lease, deadline, αποτέλεσμα και IP.
- `karta_card_listener_attempt`: κάθε προσπάθεια listener/erganiOS.
- `karta_declaration`: `submission_channel`, `submission_ip`, `executor_instance`.

```powershell
python scripts/run_migration_card_listener.py
python scripts/run_migration_submission_network_identity.py
```

Το `client_ip` είναι η IP του χρήστη που ζήτησε το χτύπημα. Το `submission_ip` είναι η
IP του executor που κάλεσε την ΕΡΓΑΝΗ.

## IP και πολλαπλοί erganiOS servers

Κάθε server node πρέπει να έχει:

```env
SERVER_INSTANCE_ID=erganios-node-01
ERGANI_EGRESS_IP=203.0.113.10
```

Η server IP διαβάζεται μόνο από config. Δεν γίνεται IP lookup στη διαδικασία χτυπήματος.

Ο listener αναγνωρίζει τη δημόσια IP μέσω `https://api.ipify.org/?format=json` και την ενημερώνει κατά την εκκίνηση και κάθε 5 λεπτά μέσω
`POST /api/card-listener/v1/network/refresh`. Η τελευταία IP κρατιέται στη μνήμη και
στο device row. Η τιμή του ipify έχει προτεραιότητα έναντι της απάντησης του backend και
απορρίπτονται loopback/private τιμές, όπως `127.0.0.1`. Η υποβολή χτυπήματος δεν κάνει IP lookup.

## Περιβάλλον ΕΡΓΑΝΗ

Το authenticated health response επιστρέφει `ergani_env`, ελληνική ετικέτα και API base
URL του καταστήματος. Ο listener v0.3.8 εμφανίζει το περιβάλλον σε disabled πεδίο `Ergani API` κάτω
από το `Usertype` κατά τον έλεγχο pairing.

Η εκτέλεση job χρησιμοποιεί το `ergani_api_base_url` του job, το οποίο παράγεται από το
περιβάλλον ΕΡΓΑΝΗ του συγκεκριμένου καταστήματος.

## Dispatcher και fallback

- Δημιουργείται idempotent job μόνο για `WRKCardSE` και μόνο όταν ο επιλεγμένος listener είναι online.
- Στην παραπάνω ροή περιλαμβάνονται οι χειροκίνητες υποβολές και το
  προγραμματισμένο αυτόματο κλείσιμο προηγούμενης ημέρας.
- Το HTTP request περιμένει μέχρι το `listener_offline_seconds` για το αποτέλεσμα του listener.
- Αν το job παραμένει `queued`, ακυρώνεται atomically και εκτελείται η υπάρχουσα απευθείας ροή erganiOS.
- Αν ο listener έχει ήδη κάνει lease/submission, δεν ξεκινά δεύτερη απευθείας υποβολή, ώστε να μην
  προκύψει διπλό χτύπημα. Αποτυχία αβέβαιης έκβασης σημειώνεται `needs_review`.
- Το αποτέλεσμα του listener αποθηκεύεται στην `karta_declaration` με `submission_channel=listener`,
  τη δημόσια IP του listener και το device που το εκτέλεσε. Η απευθείας ροή συνεχίζει να αποθηκεύει
  την configured IP και το instance id του εκάστοτε erganiOS server.
- Σε κάθε διαδραστικό σημείο υποβολής εμφανίζεται άμεσα ότι το αίτημα μπήκε σε εκτέλεση, elapsed
  timer ανά δευτερόλεπτο, ένδειξη ελέγχου fallback στα 60″ και τελικό κανάλι εκτέλεσης. Τα κουμπιά
  παραμένουν κλειδωμένα όσο εκκρεμεί η απόκριση, ώστε να αποφεύγεται δεύτερη υποβολή.

## Windows listener v0.3.8

- Project: `listener/Erganios.Listener/`.
- Self-contained compressed single-file Win-x64 executable.
- Γραφικό setup και έλεγχος pairing/credentials.
- Credentials με DPAPI LocalMachine.
- Εγκατάσταση στο `C:\Program Files\erganiOS Listener`.
- Configuration στο `C:\ProgramData\erganiOS Listener\config.json`.
- Windows Service `erganiOSListener`, automatic start και recovery.
- ACL μόνο για SYSTEM και Administrators.
- Το setup ζητά elevation κατά την εκκίνηση, ώστε να διαβάζει και να ενημερώνει πάντα
  το προστατευμένο `C:\ProgramData\erganiOS Listener\config.json` της υπηρεσίας.
- Long polling, ένα job κάθε φορά, χωρίς τοπική βάση ή εισερχόμενο port.
- Resizable/scrollable setup form που περιορίζεται στο διαθέσιμο Windows working area για μικρές αναλύσεις και υψηλό DPI.

Build:

```powershell
dotnet restore listener/Erganios.Listener/Erganios.Listener.csproj
dotnet publish listener/Erganios.Listener/Erganios.Listener.csproj -c Release --no-restore
```

## Εγκατάσταση

1. Deploy/restart του backend.
2. Ρυθμίσεις καταστήματος → **Νέο pairing**.
3. Διπλό κλικ στο `erganios-listener.exe`.
4. Συμπλήρωση Device ID/token και API credentials (`Usertype 01`, προεπιλεγμένο).
5. **Έλεγχος και αποθήκευση**.
6. Έλεγχος disabled πεδίου **Περιβάλλον Ergani API**.
7. **Εγκατάσταση υπηρεσίας** και αποδοχή UAC.

Για αναβάθμιση ανοίγουμε το νέο executable και επιλέγουμε
**Εκκίνηση/επανεγκατάσταση**.

## Έλεγχοι

- Backend regression suite: 216 tests πέρασαν, εξαιρώντας το γνωστό ανεξάρτητο test που
  ανοίγει πραγματική DB σύνδεση αντί για πλήρες mock.
- Listener v0.3.8: πλήρες globalization support για Windows cultures (`el-GR`), σύγχρονο setup UI
  με κύλιση για μικρές αναλύσεις, προεπιλεγμένο `Usertype 01`, status banner/service badge και επιτυχές restore/publish.
- Tests για store isolation, network refresh και trial environment health response.
