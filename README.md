# karta-ergani

Υπηρεσία ψηφιακής κάρτας (WRKCardSE) — MSSQL ergani-karta, pyodbc μόνο.

## Γρήγορη εκκίνηση

Ρυθμίσεις: `config.py` + `.env`

```bash
pip install -r requirements.txt
python scripts/apply_schema.py
python run.py
```

## Τεκμηρίωση

- [Project state](docs/PROJECT_STATE.md): τρέχουσα εικόνα εφαρμογής και βασικές ροές.
- [Access control](docs/ACCESS_CONTROL.md): ρόλοι/δικαιώματα (π.χ. λογιστής: Αργίες + Απολογιστικό στις Ρυθμίσεις).
- [Architecture](docs/ARCHITECTURE.md): πώς χωρίζονται routes, services, repos, UI και sync.
- [Runbook](docs/RUNBOOK.md): καθημερινές ενέργειες λειτουργίας/ελέγχου.
- [Ergani portal sync](docs/ERGANI_PORTAL_SYNC.md): portal parsing, Excel/grid fallback και sync ροές.
- [Τοπικός listener κάρτας](docs/CARD_LISTENER.md): pairing, store isolation, IP audit, Windows Service και rollout status.
- [AI Agent](docs/TELEGRAM_ASSISTANT.md): ενιαίο UI/Telegram chat, Gemini parsing, εκτέλεση και πρωτόκολλα.
- [Deployment](docs/DEPLOYMENT.md): IIS/production σημειώσεις και ρυθμίσεις.
- [Decisions](docs/DECISIONS.md): τεχνικές αποφάσεις που πρέπει να μείνουν ορατές.
- [Changelog](CHANGELOG.md): ιστορικό αλλαγών, νέα πρώτα.
- [Card Scanner PWA](docs/SCANNER_PWA.md): `/scanner/` για Android/iOS, σάρωση QR και συγχρονισμό εκκρεμοτήτων.
