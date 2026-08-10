# Τοπικός listener ψηφιακής κάρτας

## Σκοπός και τρέχουσα κατάσταση

Ο listener είναι Windows client για υποβολές `WRKCardSE` από τη δημόσια IP της
επιχείρησης. Η λειτουργία είναι πρόσθετη, ρυθμίζεται ανά κατάστημα και δεν αφορά καμία
άλλη υπηρεσία ΕΡΓΑΝΗ.

Έχουν υλοποιηθεί schema, ρυθμίσεις, pairing, device isolation, listener API και Windows
listener v0.3.1. Ο dispatcher που μετατρέπει το υφιστάμενο αίτημα χτυπήματος σε listener
job δεν έχει ακόμη συνδεθεί. Μέχρι τότε όλα τα χτυπήματα συνεχίζουν από το υπάρχον
erganiOS path.

## Ρυθμίσεις καταστήματος

Στο `karta_store_config`:

- `card_submission_mode`: `erganios` ή `listener` (default `erganios`).
- `listener_offline_seconds`: default 60, επιτρεπτό 15–600.

Στις **Ρυθμίσεις → Listener ψηφιακής κάρτας** υπάρχουν αποθήκευση παραμέτρων, νέο
pairing, κατάσταση και ανάκληση. Επιτρέπεται ένας ενεργός listener ανά κατάστημα.

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

Ο listener ενημερώνει τη δημόσια IP κατά την εκκίνηση και κάθε 5 λεπτά μέσω
`POST /api/card-listener/v1/network/refresh`. Η τελευταία IP κρατιέται στη μνήμη και
στο device row. Η υποβολή χτυπήματος δεν κάνει IP lookup.

## Περιβάλλον ΕΡΓΑΝΗ

Το authenticated health response επιστρέφει `ergani_env`, ελληνική ετικέτα και API base
URL του καταστήματος. Ο listener v0.3.1 εμφανίζει το περιβάλλον σε disabled πεδίο κάτω
από το `Usertype` κατά τον έλεγχο pairing.

Η εκτέλεση job χρησιμοποιεί το `ergani_api_base_url` του job. Η παραγωγή jobs από το
`ergani_env` θα ολοκληρωθεί μαζί με τον dispatcher.

## Windows listener v0.3.1

- Project: `listener/Erganios.Listener/`.
- Self-contained compressed single-file Win-x64 executable.
- Γραφικό setup και έλεγχος pairing/credentials.
- Credentials με DPAPI LocalMachine.
- Εγκατάσταση στο `C:\Program Files\erganiOS Listener`.
- Configuration στο `C:\ProgramData\erganiOS Listener\config.json`.
- Windows Service `erganiOSListener`, automatic start και recovery.
- ACL μόνο για SYSTEM και Administrators.
- Long polling, ένα job κάθε φορά, χωρίς τοπική βάση ή εισερχόμενο port.

Build:

```powershell
dotnet restore listener/Erganios.Listener/Erganios.Listener.csproj
dotnet publish listener/Erganios.Listener/Erganios.Listener.csproj -c Release --no-restore
```

## Εγκατάσταση

1. Deploy/restart του backend.
2. Ρυθμίσεις καταστήματος → **Νέο pairing**.
3. Διπλό κλικ στο `erganios-listener.exe`.
4. Συμπλήρωση Device ID/token και API credentials (`Usertype 02`).
5. **Έλεγχος και αποθήκευση**.
6. Έλεγχος disabled πεδίου **Περιβάλλον Ergani API**.
7. **Εγκατάσταση υπηρεσίας** και αποδοχή UAC.

Για αναβάθμιση ανοίγουμε το νέο executable και επιλέγουμε
**Εκκίνηση/επανεγκατάσταση**.

## Έλεγχοι

- Backend regression suite: 216 tests πέρασαν, εξαιρώντας το γνωστό ανεξάρτητο test που
  ανοίγει πραγματική DB σύνδεση αντί για πλήρες mock.
- Listener v0.3.1: επιτυχές restore/publish.
- Tests για store isolation, network refresh και trial environment health response.
