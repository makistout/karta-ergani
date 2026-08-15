# Telegram assistant — Gemini dry-run commands

## Τρέχουσα φάση

Το `POST /api/telegram/webhook` δέχεται κανονικά μηνύματα μόνο από `chat_id` που
ανήκουν σε ενεργό λήπτη του `karta_store_notify_recipient`. Άγνωστα `chat_id`
αγνοούνται χωρίς αποθήκευση και χωρίς απάντηση.

Τα αποδεκτά μηνύματα αναλύονται από Gemini σε αυστηρό JSON. Οι έγκυρες εντολές
αποθηκεύονται ως `awaiting_confirmation`, ενώ οι ασαφείς ως
`needs_clarification`. **Δεν υπάρχει διαδρομή εκτέλεσης ή αποστολής προς
ΕΡΓΑΝΗ** και κάθε task γράφεται με `execution_enabled=0`.

## Ροή επιβεβαίωσης

Για έγκυρη εντολή η συνομιλία προχωρά deterministic, χωρίς νέες κλήσεις Gemini:

1. εμφανίζεται ο αριθμός εντολής και η πλήρης προτεινόμενη ενέργεια,
2. ζητείται απάντηση `ΝΑΙ` ή `ΟΧΙ`,
3. το `ΟΧΙ` ακυρώνει την εντολή, ενώ το `ΝΑΙ` ζητά τον προσωπικό 4ψήφιο PIN,
4. ο σωστός PIN αλλάζει την κατάσταση σε `confirmed_dry_run` και εμφανίζει τι
   **ΘΑ** εκτελεστεί όταν ενεργοποιηθεί η υπηρεσία.

Οι απαντήσεις μπορούν να σταλούν ως reply στο σχετικό bot μήνυμα. Για σύντομες
απαντήσεις `ΝΑΙ`, `ΟΧΙ` ή τετραψήφιο PIN υποστηρίζεται επίσης το πιο πρόσφατο
pending task του ίδιου εξουσιοδοτημένου chat. Τα βήματα επιβεβαίωσης δεν
ξαναστέλνονται στο Gemini.

Ο PIN δεν αποθηκεύεται στο κείμενο ή στο raw JSON του Telegram update και δεν
γράφεται στα task events. Μετά από πέντε λανθασμένες προσπάθειες η εντολή
κλειδώνει. Ακόμη και μετά από σωστό PIN δεν εκτελείται τίποτα στο ΕΡΓΑΝΗ στην
τρέχουσα φάση.

Υποστηριζόμενες προθέσεις πρώτης φάσης:

- άνοιγμα/κλείσιμο κάρτας τώρα,
- άνοιγμα/κλείσιμο κάρτας προγενέστερα,
- αλλαγή ημερήσιου ωραρίου,
- ρεπό,
- άδεια (απαιτείται τύπος άδειας).

Κάθε πρόθεση μπορεί να αφορά έναν ή περισσότερους εργαζομένους, π.χ.
`άνοιξε τις κάρτες του Βήχου και του Hoxha 10 λεπτά πριν`. Οι εργαζόμενοι
αποθηκεύονται ως λίστα ΑΦΜ στο JSON payload του ίδιου dry-run task.

Αν λείπει μοναδικό κατάστημα, αν δεν αντιστοιχιστούν μοναδικά όλοι οι
εργαζόμενοι, ή αν λείπει ημερομηνία, ώρα ή τύπος άδειας, το
task αποθηκεύεται ως `needs_clarification`. Σε reply περιλαμβάνεται στο Gemini
context και το κείμενο του αρχικού Telegram μηνύματος.

## Πίνακες

- `karta_telegram_inbound_message`: εισερχόμενα updates και idempotency μέσω
  μοναδικού `telegram_update_id`.
- `karta_telegram_outbound_message`: απεσταλμένα Telegram message IDs και reply
  context.
- `karta_assistant_task`: δομημένη πρόθεση, validation, περιγραφή ενέργειας και
  κατάσταση συνομιλίας (`awaiting_confirmation`, `awaiting_pin`,
  `confirmed_dry_run`, `cancelled`, `pin_locked` ή `needs_clarification`).
  Για κάθε επιτυχημένο Gemini request αποθηκεύει επίσης model, διάρκεια και
  token usage (`prompt`, `candidates`, `total`, `cached content`, `thoughts`,
  `tool-use prompt`) μαζί με το πλήρες `usageMetadata` JSON.
- `karta_assistant_task_event`: append-only ιστορικό task.

Migration:

```bash
python scripts/run_migration_telegram_assistant.py
```

## Ρυθμίσεις

```env
GEMINI_API_KEY=
GEMINI_MODEL=gemini-flash-latest
TELEGRAM_ASSISTANT_ENABLED=1
```

Το API key δεν αποθηκεύεται στη βάση ή στο Git. Η σταθερά
`TELEGRAM_ASSISTANT_EXECUTION_ENABLED` παραμένει `False` στην πρώτη φάση.

## Ασφάλεια

- Το Gemini επιλέγει μόνο από καταλόγους επιτρεπόμενων καταστημάτων και
  εργαζομένων που δίνει ο server.
- Η έξοδος επανελέγχεται deterministic πριν αποθηκευτεί.
- Οι ημερομηνίες ελέγχονται ως πραγματικές ημερολογιακές τιμές και όχι μόνο ως
  συμβολοσειρές μορφής `YYYY-MM-DD`.
- Telegram retries δεν δημιουργούν δεύτερο inbound message ή task.
- Κάθε μετάβαση task απαιτεί την αναμενόμενη προηγούμενη κατάσταση και
  `execution_enabled=0`.
- Η επαλήθευση PIN συνδέει task, αρχικό inbound chat και ενεργό λήπτη πριν από
  οποιαδήποτε αλλαγή κατάστασης.
- Τα token counts προέρχονται από το `usageMetadata` της ίδιας της απόκρισης
  Gemini· δεν υπολογίζονται προσεγγιστικά από τον server. Η τιμολόγηση δεν
  αποθηκεύεται, επειδή μεταβάλλεται ανεξάρτητα από τα ιστορικά usage δεδομένα.
- Τα σφάλματα Gemini αποθηκεύονται στο inbound message, χωρίς να εκτελείται
  fallback ενέργεια.
