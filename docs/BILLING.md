# Τιμολογήσεις

Απομονωμένο module. Δεν αλλάζει καταστήματα, κάρτα, απολογιστικό ή scanner.
Μόνο `super_admin` (`billing.manage`).

## Μενού

Υπομενού κάτω από **Τιμολογήσεις** (εσοχή, μικρότερα γράμματα, bullet):

- **Πελάτες** `/ui/billing` — αναζήτηση με το ίδιο autocomplete (επωνυμία / ΑΦΜ).
- **Συνδρομές** `/ui/billing/subscriptions` — κατάλογος **πακέτων** (όχι έκδοση).
- **Τιμολόγια** `/ui/billing/invoices` — επιλογή συνδρομών και έκδοση.
- **Παρουσιάσεις** `/ui/billing/presentations` — πάνω αριστερά μικρό πεδίο
  email και κουμπί **Αποστολή** στην ίδια γραμμή. Κάτω προεπισκόπηση των
  δύο PDF. `POST /api/billing/presentation` μετά από έλεγχο μορφής, BCC
  `info@erganios.gr`. PDF: `GET /api/billing/presentation/files/<key>`.

Η καρτέλα πελάτη έχει στοιχεία (και **Εκπρόσωπο**), καταστήματα, συνδρομές και
παραστατικά. Τα κουμπιά **Προσφορά** και **Συμφωνητικό** κατεβάζουν συμπληρωμένα
Word (`POST /api/billing/offer`, `POST /api/billing/agreement`) από
`app/private/billing/prosfora_erganios.docx` και
`app/private/billing/symfonitiko_analipsis_efthynis.docx`. Χωρίς εκπρόσωπο δεν
κατεβαίνουν. Προσφορά: Προς = επωνυμία, ημερομηνία = σήμερα. Συμφωνητικό:
Πάροχος = `BILLING_ISSUER_*`, Εργοδότης = επωνυμία / ΑΦΜ / έδρα / εκπρόσωπος.
Το **Αποστολή παρουσίασης** στέλνει στο καταχωρημένο email τα PDF
`erganiOS_apologistiko_orometrisi.pdf` και `erganiOS_AI-Agent.pdf`
(`POST /api/billing/presentation`). Χωρίς email δεν στέλνει. Υπογραφή:
`BILLING_CONTACT_NAME` / `BILLING_CONTACT_PHONE` / `BILLING_ISSUER_EMAIL` /
`PUBLIC_BASE_URL` (αλλιώς erganiOS, 6977392742, info@erganios.gr,
https://erganios.gr). Η γραμμή ιστοτόπου γράφεται `Web: …`. BCC `info@erganios.gr`.

## Πακέτα (Συνδρομές)

Ομαδοποίηση ανά οικογένεια (π.χ. ErganiOS + Απολογιστικό 12 μήνες) με αυξουσα τιμή.
Όλα τα γκρουπ ξεκινούν **collapsed** (`+` / `−`). Μοναδικό όνομα πακέτου.
Ενεργό = διακόπτης, αποθήκευση = δισκέτα, αντιγραφή = duplicate.

## Έκδοση τιμολογίου

Η επιλογή πακέτων γίνεται **στην έκδοση**, όχι στη σελίδα Συνδρομές. Μετά
καταχωρείται στην καρτέλα του πελάτη.

1. Πελάτης (autocomplete) + τύπος / σειρά / έναρξη (`ηη/μμ/εεεε`).
2. Γκρουπ πακέτων collapsed· με `+` ανοίγουν μία γραμμή το καθένα.
   Επιλεγμένη γραμμή γίνεται γκρι. Κλικ στην τιμή → modal μόνο για αυτό το
   παραστατικό (όχι αλλαγή καταλόγου)· η αλλαγή ποσού επιλέγει τη γραμμή,
   η ξε-επιλογή επαναφέρει την τιμή καταλόγου.
3. **Έκδοση** κάτω από τη λίστα.
4. Τύπος ΑΠΥ `11.2` ή ΤΠΥ `2.1`.
5. `POST /v2/invoices` στο `https://sandbox-api.mydataprovider.gr/v2`
   με Bearer API key, όπως στο `room/oxygen` (`spot=0`).
6. Αποθήκευση `mark`, `uid`, `url` (iview/QR).

Χωρίς `OXYGEN_API_KEY` το παραστατικό σώζεται μόνο τοπικά.

## Πιστωτικό (Oxygen, όπως room spot=0)

Κουμπί **Πιστωτικό** μόνο σε εκδοθέν ΑΠΥ/ΤΠΥ χωρίς πιστωτικό (`Office.confirm`):

- ΤΠΥ → τύπος `5.1` + `correlated_documents` = Oxygen id του αρχικού.
- ΑΠΥ → τύπος `11.4` + ίδια συσχέτιση.
- Σειρά `Π`, ποσά θετικά στο JSON.
- Ένα πιστωτικό ανά παραστατικό. Οι συνδρομές του αρχικού ακυρώνονται.

Όταν έχει ήδη εκδοθεί πιστωτικό, στη στήλη εμφανίζεται ο **αριθμός** του
(π.χ. `Π-1`) ως κείμενο, χωρίς link.

## Έντυπο προς πελάτη

`/ui/billing/invoice/<id>` — Α4: εκδότης αριστερά, λογότυπο δεξιά, στοιχεία
πελάτη / παραστατικού, γραμμές (όνομα πακέτου χωρίς εύρος ημερομηνιών),
παρατηρήσεις+τράπεζες, σύνολα, από κάτω QR αριστερά και UID/MARK/Auth/ICODE
+ πάροχος δεξιά. Τα `BILLING_ISSUER_*` / `BILLING_BANK_*` στο `.env` είναι
ενδεικτικά μέχρι τα πραγματικά στοιχεία. Το `qrcode` πρέπει να είναι στο
IIS venv.

Έντυπο και Oxygen PDF ανοίγουν με εικονίδια στη λίστα.

## Μετανάστευση

```powershell
python -X utf8 scripts/run_migration_billing.py
```

Η στήλη `representative` είναι στο `sql/alter_add_billing.sql` (και στο
`sql/alter_add_billing_customer_representative.sql` για υπάρχουσες βάσεις).

Στοιχεία υπογραφής παρουσίασης στο `.env`: `BILLING_CONTACT_NAME`,
`BILLING_CONTACT_PHONE`, `BILLING_ISSUER_EMAIL`, `PUBLIC_BASE_URL`.
