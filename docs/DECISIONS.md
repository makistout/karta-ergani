# Decisions

## Changelog vs Living Docs

Το `CHANGELOG.md` κρατά ιστορικό αλλαγών. Η τρέχουσα τεχνική εικόνα μεταφέρεται στα `docs/*.md`.

## Compatibility Facades

Όταν μεγάλο module χωρίζεται, το αρχικό filename μπορεί να παραμένει ως facade που κάνει import/re-export τις public functions. Αυτό μειώνει το ρίσκο σε routes/tests/scripts που ήδη εισάγουν το παλιό module.

## Empty Work Log Sync

Κενή πραγματική απασχόληση από portal δεν είναι απαραίτητα σφάλμα. Η εφαρμογή το αντιμετωπίζει ως επιτυχημένο sync με `count=0` όταν δεν υπάρχουν πραγματικές καταγραφές.

## Notification Links

Τα Telegram/Email recipient links πρέπει να είναι public absolute URLs. Τα redirects μετά από PIN πρέπει να είναι relative paths ώστε να μένουν στο ίδιο host.

## Frontend Strategy

Το shared UI shell ανήκει σε templates. Το page-specific behavior μένει σε ξεχωριστό JS ανά σελίδα. Κοινά browser helpers μπαίνουν σε μικρά shared JS modules και εκτίθενται μέσω του global `Office` για συμβατότητα.
