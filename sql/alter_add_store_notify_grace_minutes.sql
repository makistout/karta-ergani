/*
  Καθυστέρηση ειδοποιήσεων (λεπτά) ανά κατάστημα — 15, 30 ή 45.
  Χρησιμοποιείται για late_check_in / late_check_out / exit_needs_correction grace.
*/

IF COL_LENGTH(N'dbo.karta_store_config', N'notify_grace_minutes') IS NULL
BEGIN
    ALTER TABLE dbo.karta_store_config
        ADD notify_grace_minutes INT NOT NULL
            CONSTRAINT DF_karta_store_notify_grace_minutes DEFAULT (15);
    PRINT N'OK: notify_grace_minutes';
END
GO
