# Deployment

## Runtime

- Flask app μέσω `wsgi.py`.
- MSSQL μέσω `pyodbc`.
- Ρυθμίσεις από `config.py` και `.env`.
- IIS configuration στο `web.config`.

## Public URLs

Τα δημόσια links Telegram/Email πρέπει να παράγονται από `app/public_urls.py`.

Σε production δεν πρέπει να βγαίνουν links προς `localhost`.

Το canonical public marketing URL είναι **`https://erganios.gr/`**. Το `/psifiaki-karta-ergasias/` κάνει 301 στο `/` (το `/ui/landing` επίσης 301 στο `/`).
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

## Φόρμα επικοινωνίας landing

Ροή: φόρμα `#contact` → `POST /api/contact` → `send_email_message()` → SMTP Mailgun.

| Ρύθμιση | Περιγραφή |
|---------|-----------|
| `SMTP_HOST` | Mailgun SMTP (π.χ. `smtp.eu.mailgun.org`) |
| `SMTP_FROM_EMAIL` / `SMTP_FROM_NAME` | Αποστολέας (π.χ. `noreply@erganios.gr`) |
| `CONTACT_TO_EMAIL` | Σταθερά `info@erganios.gr` στο `routes_contact.py` |

**Διάγνωση αν δεν φτάνει email:**

1. Η φόρμα έδειξε «Θα επικοινωνήσουμε σύντομα»; Αν όχι, μπορεί να πυροδοτήθηκε honeypot (`website`) ή SMTP error (502/503).
2. Έλεγξε **Mailgun → Logs** για accepted/delivered/bounced.
3. Έλεγξε **spam** και ότι υπάρχει mailbox `info@` στο `mail.erganios.gr` (MX του `erganios.gr`).
4. DNS: SPF πρέπει να περιλαμβάνει `include:mailgun.org`.

Μετά από αλλαγές CSS landing, ενημέρωσε cache-bust στο `office.css`.
