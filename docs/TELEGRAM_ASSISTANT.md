# Telegram assistant — Gemini dry-run commands

## Τρέχουσα φάση

Το `POST /api/telegram/webhook` δέχεται κανονικά μηνύματα μόνο από `chat_id` που
ανήκουν σε ενεργό λήπτη του `karta_store_notify_recipient`. Άγνωστα `chat_id`
αγνοούνται χωρίς αποθήκευση και χωρίς απάντηση.

Τα αποδεκτά μηνύματα αναλύονται από Gemini σε αυστηρό JSON και αποθηκεύονται ως
draft tasks. **Δεν υπάρχει διαδρομή εκτέλεσης ή αποστολής προς ΕΡΓΑΝΗ** και κάθε
task γράφεται με `execution_enabled=0`.

Υποστηριζόμενες προθέσεις πρώτης φάσης:

- άνοιγμα/κλείσιμο κάρτας τώρα,
- άνοιγμα/κλείσιμο κάρτας προγενέστερα,
- αλλαγή ημερήσιου ωραρίου,
- ρεπό,
- άδεια (απαιτείται τύπος άδειας).

Αν λείπει μοναδικό κατάστημα, εργαζόμενος, ημερομηνία, ώρα ή τύπος άδειας, το
task αποθηκεύεται ως `needs_clarification`. Σε reply περιλαμβάνεται στο Gemini
context και το κείμενο του αρχικού Telegram μηνύματος.

## Πίνακες

- `karta_telegram_inbound_message`: εισερχόμενα updates και idempotency μέσω
  μοναδικού `telegram_update_id`.
- `karta_telegram_outbound_message`: απεσταλμένα Telegram message IDs και reply
  context.
- `karta_assistant_task`: δομημένη πρόθεση, validation, περιγραφή ενέργειας και
  κατάσταση draft.
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
- Τα σφάλματα Gemini αποθηκεύονται στο inbound message, χωρίς να εκτελείται
  fallback ενέργεια.
