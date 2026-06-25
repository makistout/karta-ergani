/*
  Migration: πολιτική επανάληψης ειδοποιήσεων ανά λήπτη.
  - once_snooze: ο λήπτης ειδοποιείται μία φορά και μετά γράφεται snooze.
  - repeat_until_action: ο λήπτης ειδοποιείται σε κάθε post-sync μέχρι snooze/ενέργεια.
*/
SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
GO

IF OBJECT_ID(N'dbo.karta_store_notify_recipient', N'U') IS NULL
BEGIN
    RAISERROR(N'Λείπει ο πίνακας dbo.karta_store_notify_recipient. Τρέξτε πρώτα sql/alter_add_store_notify_recipients.sql.', 16, 1);
END
GO

IF COL_LENGTH(N'dbo.karta_store_notify_recipient', N'notify_repeat_policy') IS NULL
BEGIN
    ALTER TABLE dbo.karta_store_notify_recipient
        ADD notify_repeat_policy NVARCHAR(32) NOT NULL
            CONSTRAINT DF_karta_notify_repeat_policy DEFAULT (N'once_snooze');
    PRINT N'OK: karta_store_notify_recipient.notify_repeat_policy';
END
GO
