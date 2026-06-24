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

Πριν από production run:

- επιβεβαίωσε `.env`,
- επιβεβαίωσε MSSQL permissions,
- τρέξε το αντίστοιχο `scripts/run_migration_*.py`,
- κράτα σημείωση στο `CHANGELOG.md`.

## Sync Operations

- Manual sync από `/ui/sync`.
- Scheduled sync μέσω `scripts/run_scheduled_sync.py`.
- Sync logs από `/ui/sync-log`.
- Post-sync Telegram/Email notifications καταγράφονται ως ξεχωριστή operation.

## Common Failure Checks

- Λάθος active store ή credentials.
- Portal URL/environment mismatch.
- Κενό Excel/grid από portal.
- Expired Telegram/Email token ή PIN lock.
- SMTP/Telegram configuration στο `.env`.
