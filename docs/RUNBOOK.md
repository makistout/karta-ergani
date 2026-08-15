# Runbook

## Local Startup

```bash
python scripts/apply_schema.py
python run.py
```

Σε αυτό το repo υπάρχει `.venv`, οπότε συνήθως:

```bash
.venv/bin/python run.py
```

## Sanity Checks

Syntax check χωρίς write σε macOS user cache:

```bash
env PYTHONPYCACHEPREFIX=/private/tmp/karta_pycache .venv/bin/python -m compileall -q app scripts tests run.py wsgi.py config.py
```

Unit tests, όταν είναι εγκατεστημένο το `pytest`:

```bash
.venv/bin/python -m pytest -q
```

## Database Migrations

Τα SQL migrations ζουν στο `sql/` και οι runners στο `scripts/`.

- Telegram assistant: `python scripts/run_migration_telegram_assistant.py`.

Πριν από production run:

- επιβεβαίωσε `.env`,
- επιβεβαίωσε MSSQL permissions,
- τρέξε το αντίστοιχο `scripts/run_migration_*.py`,
- κράτα σημείωση στο `CHANGELOG.md`.

## Sync Operations

- Manual sync από `/ui/sync`.
- Scheduled sync μέσω `scripts/run_scheduled_sync.py`.
- Το scheduled sync κάνει στο βασικό run σημερινό ωράριο/πραγματική και, μία φορά μετά τα
  μεσάνυχτα/ώρα auto-close ανά κατάστημα, ξεχωριστό sync ψηφιακού ωραρίου για αύριο και
  μεθαύριο (`scheduled_future_schedule_sync`).
- Επιπλέον τρέχει αυτόματα:
  - νυχτερινό `30ήμερο` sync πραγματικής για όλα τα καταστήματα
    (`scheduled_recent_work_log_sync`, προεπιλογή `03:00`)
  - νυχτερινό sync πρωτοκόλλων Ergani + 1-1 απαγωγή για χθες
    (`scheduled_nightly_protocol_sync`, προεπιλογή `03:00`, μετά το 30ήμερο πραγματικής)
  - ημερήσιο sync στοιχείων σύμβασης από Μητρώα
    (`scheduled_employment_contract_sync`, προεπιλογή `04:00`)
  - κυριακάτικο `90ήμερο` repair sync πραγματικής
    (`scheduled_weekly_repair_work_log_sync`, προεπιλογή `05:00`)
- Αν λείπει ο πίνακας συμβάσεων: `python scripts/ensure_karta_employment_contract_table.py`
  ή `sql/alter_add_karta_employment_contract.sql`.
- Αν λείπουν πρωτόκολλα Ergani / στήλες πραγματικής:
  `python scripts/ensure_karta_ergani_protocol_table.py`,
  `python scripts/ensure_work_log_protocol_columns.py`
  ή τα αντίστοιχα `sql/alter_add_*.sql`.
- Οι νέες φάσεις γράφουν ξεχωριστά runs στα sync logs και προστατεύονται με ημερήσιο /
  εβδομαδιαίο guard ώστε να εκτελούνται μία φορά ανά κατάστημα.
- Sync logs από `/ui/sync-log`.
- Post-sync Telegram/Email notifications καταγράφονται ως ξεχωριστή operation.

## Common Failure Checks

- Λάθος active store ή credentials.
- Portal URL/environment mismatch.
- Κενό Excel/grid από portal.
- Expired Telegram/Email token ή PIN lock.
- SMTP/Telegram configuration στο `.env`.
- Φόρμα landing `/api/contact`: αν επιστρέφει επιτυχία αλλά δεν φτάνει email, έλεγξε Mailgun logs και mailbox `info@erganios.gr` (βλ. `DEPLOYMENT.md`).
