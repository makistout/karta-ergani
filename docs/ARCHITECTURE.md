# Architecture

## Backend

Η εφαρμογή είναι Flask app με factory στο `app/__init__.py`.

- `app/routes_*.py`: HTTP endpoints και request/response handling.
- `app/repo_*.py`: SQL access και database-specific mapping.
- `app/*_service.py`, `app/*_sync.py`: business flows και orchestration.
- `app/*_payload.py`: κατασκευή/validation payloads προς Ergani.
- `app/portal_*.py`: portal automation/parsing και Excel/grid fallback.
- `app/templates/ui`: Flask templates για το runtime UI.
- `app/static/js`: page scripts και shared browser helpers.
- `app/static/css`: shared και feature CSS.

## Dependency Direction

Προτιμώμενη φορά εξαρτήσεων:

1. routes καλούν services/repos,
2. services καλούν repos και payload helpers,
3. repos δεν καλούν routes/services,
4. UI JS καλεί μόνο public API endpoints,
5. shared JS/CSS δεν πρέπει να ξέρει page-specific state εκτός αν είναι πραγματικά κοινό component.

## Module Split Rules

- Αν ένα αρχείο ξεπερνά περίπου 500-700 γραμμές, ελέγχουμε αν έχει πολλούς ρόλους.
- Δεν χωρίζουμε μόνο με βάση το μέγεθος. Χωρίζουμε όταν υπάρχει καθαρό ownership boundary.
- Σε risky refactors, κρατάμε facade module που κάνει re-export τις παλιές public functions.
- Κάθε split συνοδεύεται από compile/test pass πριν μπει νέα συμπεριφορά.

## Frontend Shell

Το UI χρησιμοποιεί shared template shell:

- `base.html`: head/body/layout και shared CSS/JS loading.
- `_sidebar.html`: κοινή πλοήγηση.
- page templates: μόνο το main content και page-specific scripts.

Τα public recipient pages χρησιμοποιούν standalone layout χωρίς sidebar.
