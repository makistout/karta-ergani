# Deployment

## Runtime

- Flask app μέσω `wsgi.py`.
- MSSQL μέσω `pyodbc`.
- Ρυθμίσεις από `config.py` και `.env`.
- IIS configuration στο `web.config`.

## Public URLs

Τα δημόσια links Telegram/Email πρέπει να παράγονται από `app/public_urls.py`.

Σε production δεν πρέπει να βγαίνουν links προς `localhost`.

Το canonical public marketing URL είναι **`/psifiaki-karta-ergasias/`** (το `/ui/landing` κάνει 301).
Μετά από αλλαγές σε routes/templates του landing, κάνε recycle του IIS app pool (`erganios.gr`).

## Static Assets

Το UI φορτώνει CSS/JS από `/static`.

Μετά από αλλαγές σε browser assets:

- ενημέρωσε cache-bust query string όπου χρειάζεται,
- έλεγξε login/public recipient flows,
- έλεγξε `/ui/`, `/ui/work-log`, `/ui/stores/notify`, `/ui/work-card`.

## Environment

Κρίσιμα `.env` groups:

- database connection,
- Flask secret,
- public base URL,
- Telegram bot/webhook,
- SMTP,
- Ergani API/portal settings.
