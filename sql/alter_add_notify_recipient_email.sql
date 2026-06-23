/*
  Migration: email ληπτών ειδοποιήσεων καταστήματος
*/
SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
GO

IF OBJECT_ID(N'dbo.karta_store_notify_recipient', N'U') IS NULL
BEGIN
    RAISERROR(N'Λείπει ο πίνακας dbo.karta_store_notify_recipient. Τρέξτε πρώτα sql/alter_add_store_notify_recipients.sql.', 16, 1);
    RETURN;
END
GO

IF COL_LENGTH(N'dbo.karta_store_notify_recipient', N'email') IS NULL
BEGIN
    ALTER TABLE dbo.karta_store_notify_recipient
        ADD email NVARCHAR(254) NULL;
    PRINT N'OK: karta_store_notify_recipient.email';
END
GO

IF COL_LENGTH(N'dbo.karta_store_notify_recipient', N'email_active') IS NULL
BEGIN
    ALTER TABLE dbo.karta_store_notify_recipient
        ADD email_active BIT NOT NULL
            CONSTRAINT DF_karta_notify_email_active DEFAULT (1);
    PRINT N'OK: karta_store_notify_recipient.email_active';
END
GO
