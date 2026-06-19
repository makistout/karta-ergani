/*
  Αποθήκευση 4ψήφιου PIN λήπτη (εμφάνιση στη φόρμα καταστήματος).
  Το notify_pin_hash παραμένει για επαλήθευση στο Telegram punch.
*/
SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
GO

IF COL_LENGTH(N'dbo.karta_store_notify_recipient', N'notify_pin') IS NULL
BEGIN
    ALTER TABLE dbo.karta_store_notify_recipient
        ADD notify_pin NVARCHAR(4) NULL;
    PRINT N'OK: notify_pin';
END
GO
