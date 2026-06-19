/*
  Επιβεβαίωση PIN για retro-hit χωρίς εξάρτηση από session cookie (κινητό/Telegram).
*/
SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
GO

IF COL_LENGTH(N'dbo.karta_telegram_punch_token', N'pin_verified_at') IS NULL
BEGIN
    ALTER TABLE dbo.karta_telegram_punch_token
        ADD pin_verified_at DATETIMEOFFSET(7) NULL;
    PRINT N'OK: pin_verified_at';
END
GO
