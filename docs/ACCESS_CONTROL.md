# Access Control

Στόχος: δεν ξαναγράφουμε τις υπάρχουσες υπηρεσίες. Προσθέτουμε στρώμα δικαιωμάτων πάνω από routes, UI actions και επιλογή καταστήματος. Ο σημερινός admin γίνεται `super_admin` και συνεχίζει να έχει πρόσβαση σε όλα.

## Αρχές

- Το backend είναι η πραγματική ασφάλεια. Το UI απλώς κρύβει ή απενεργοποιεί λειτουργίες για ευκολία.
- Κάθε χρήστης έχει ρόλο, granular permissions και λίστα επιτρεπόμενων `store_id`.
- Το `super_admin` βλέπει όλα τα καταστήματα και έχει όλα τα permissions.
- Για κάθε request ελέγχουμε login, permission και όπου υπάρχει store context, store access.
- Οι υπηρεσίες μένουν ως έχουν. Οι έλεγχοι μπαίνουν σε route/helper layer πριν κληθούν.

## Υλοποίηση

- `app/access_control.py`: ορίζει roles, permissions, UI/API route rules, session helpers και store-access helpers.
- `app/office_auth.py`: κάνει login από DB όταν υπάρχουν οι πίνακες χρηστών και κρατά στο session role/permissions/user id.
- `app/repo_users.py`: διαχειρίζεται users, roles, permissions, password hashes και store access.
- `app/routes_users.py`: API για λίστα/δημιουργία/ενημέρωση χρήστη, reset password, permissions και stores.
- `app/http_helpers.py` και store routes: εφαρμόζουν store scoping ώστε ο μη-super-admin να βλέπει/επιλέγει μόνο επιτρεπόμενα καταστήματα.
- `app/templates/ui/partials/_sidebar.html`: εμφανίζει navigation items μόνο όταν ο χρήστης έχει το αντίστοιχο permission.
- `scripts/run_migration_office_users.py` και `sql/alter_add_office_users.sql`: δημιουργούν schema και κάνουν seed τον σημερινό admin ως `super_admin`.

## Ρόλοι

- `super_admin`: όλα, όλα τα καταστήματα.
- `admin` / `backoffice_admin`: backoffice λειτουργίες χωρίς secrets/users by default.
- `office_manager`: λειτουργία γραφείου, sync, κάρτες, ελλιπή χτυπήματα, ειδοποιήσεις, logs στα καταστήματά του.
- `office`: καθημερινές ενέργειες χειριστή.
- `store_viewer` / `viewer`: μόνο προβολή.
- `notifications_manager`: ειδοποιήσεις και αντίστοιχα logs.

## UI Χρηστών

Η σελίδα `/ui/users` είναι το κέντρο διαχείρισης χρηστών.

- Αριστερά υπάρχει λίστα χρηστών με username, role και status.
- Η φόρμα χρήστη υποστηρίζει username, email, όνομα, role, ενεργό/ανενεργό και reset password.
- Τα καταστήματα δεν φορτώνονται ως μαζική checkbox λίστα. Ο χειριστής γράφει όνομα ή ΑΦΜ στο autocomplete, πατά Enter ή `Προσθήκη`, και το κατάστημα προστίθεται κάτω στη λίστα πρόσβασης του χρήστη.
- Η λίστα επιλεγμένων καταστημάτων δείχνει όνομα, ΑΦΜ, αριθμό εργαζομένων και κουμπί αφαίρεσης ανά γραμμή.
- Τα granular permissions εμφανίζονται ως checkbox list και μπορούν να γεμίσουν από `Template ρόλου`.
- Ο συγκριτικός πίνακας δικαιωμάτων δείχνει κάθε permission ανά τύπο/ενέργεια και συγκρίνει όλους τους ρόλους δίπλα-δίπλα με τους πραγματικούς χρήστες.
- Στον συγκριτικό πίνακα το component, η περιγραφή και ο τεχνικός κωδικός permission εμφανίζονται σε hover tooltip πάνω στην ενέργεια, ώστε ο πίνακας να μένει συμπαγής.
- Οι στήλες ρόλων έχουν σύντομες ετικέτες για να μην ανοίγει υπερβολικά το matrix, αλλά το πλήρες role φαίνεται στο hover του header.

## Σελίδες Και Permissions

- Αρχική: `dashboard.view`
- Εργαζόμενοι: `employees.view`, `employees.sync`, `employees.export`
- Ψηφιακό ωράριο: `schedule.view`, `schedule.sync`, `schedule.submit_daily`, `schedule.submit_weekly`, `schedule.submit_leave`, `schedule.export`
- Πραγματική απασχόληση: `work_log.view`, `work_log.sync`, `work_log.export`
- Ελλιπή χτυπήματα: `missing_cards.view`, `missing_cards.close_one`, `missing_cards.close_all`, `missing_cards.sync_refresh`
- Ψηφιακή κάρτα: `work_card.view`, `work_card.submit_live`, `work_card.submit_retro`, `work_card.view_history`, `work_card.sync_refresh`
- Συγχρονισμός: `sync.view`, `sync.run_store`, `sync.run_period`, `sync.run_all`, `sync.view_progress`
- Καταστήματα: `stores.view`, `stores.select`, `stores.manage`, `stores.credentials.manage`, `stores.api_env.manage`, `stores.view_sensitive`
- Ειδοποιήσεις: `notifications.view`, `notifications.recipients.manage`, `notifications.rules.manage`, `notifications.snooze`, `notifications.send_test`
- Καταγραφές: `logs.view`, `logs.view_sync`, `logs.view_notifications`, `logs.view_work_cards`, `logs.view_errors`, `logs.export`
- Χρήστες / δικαιώματα: `users.view`, `users.create`, `users.edit`, `users.disable`, `users.reset_password`, `users.manage_permissions`, `users.manage_store_access`
- Ρυθμίσεις: `settings.view`, `settings.edit`, `settings.secrets.manage`, `settings.scheduler.manage`

## Dangerous Permissions

Αυτά δεν πρέπει να δίνονται έμμεσα χωρίς σκέψη:

- `work_card.submit_live`
- `work_card.submit_retro`
- `missing_cards.close_all`
- `sync.run_all`
- `stores.credentials.manage`
- `settings.secrets.manage`
- `users.manage_permissions`

## Store Scoping

Πίνακες:

- `karta_user`
- `karta_role`
- `karta_permission`
- `karta_role_permission`
- `karta_user_permission`
- `karta_user_store`

Κανόνας: ο χρήστης βλέπει και επιλέγει μόνο καταστήματα που υπάρχουν στο `karta_user_store`, εκτός αν είναι `super_admin`.

## Φάσεις

1. RBAC layer με σημερινό config admin ως `super_admin`. Ολοκληρώθηκε.
2. DB schema για users/roles/permissions/store access και seed του σημερινού admin. Ολοκληρώθηκε.
3. Login από DB με password hashing. Ολοκληρώθηκε.
4. Store scoping σε active store, store list και routes που δέχονται store id. Ολοκληρώθηκε για το βασικό store flow.
5. Έλεγχοι πρώτα στα επικίνδυνα actions. Σε εξέλιξη καθώς συνδέονται επιπλέον routes.
6. `/ui/users` για δημιουργία χρηστών, ρόλους, permissions, store access και reset password. Ολοκληρώθηκε για την πρώτη έκδοση.
7. Audit για login/logout, permission denied και αλλαγές χρηστών. Επόμενη φάση.
