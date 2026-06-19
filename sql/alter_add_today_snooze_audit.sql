/*
  Audit αναβολής (snooze) — ποιος, IP, browser, ώρα.
*/
SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
GO

IF COL_LENGTH(N'dbo.karta_today_notify_snooze', N'acted_by_name') IS NULL
BEGIN
    ALTER TABLE dbo.karta_today_notify_snooze
        ADD acted_by_name NVARCHAR(200) NULL;
    PRINT N'OK: acted_by_name';
END
GO

IF COL_LENGTH(N'dbo.karta_today_notify_snooze', N'acted_by_mobile') IS NULL
BEGIN
    ALTER TABLE dbo.karta_today_notify_snooze
        ADD acted_by_mobile NVARCHAR(32) NULL;
    PRINT N'OK: acted_by_mobile';
END
GO

IF COL_LENGTH(N'dbo.karta_today_notify_snooze', N'acted_via') IS NULL
BEGIN
    ALTER TABLE dbo.karta_today_notify_snooze
        ADD acted_via NVARCHAR(32) NULL;
    PRINT N'OK: acted_via';
END
GO

IF COL_LENGTH(N'dbo.karta_today_notify_snooze', N'office_user') IS NULL
BEGIN
    ALTER TABLE dbo.karta_today_notify_snooze
        ADD office_user NVARCHAR(128) NULL;
    PRINT N'OK: office_user';
END
GO

IF COL_LENGTH(N'dbo.karta_today_notify_snooze', N'client_ip') IS NULL
BEGIN
    ALTER TABLE dbo.karta_today_notify_snooze
        ADD client_ip NVARCHAR(45) NULL;
    PRINT N'OK: client_ip';
END
GO

IF COL_LENGTH(N'dbo.karta_today_notify_snooze', N'client_device') IS NULL
BEGIN
    ALTER TABLE dbo.karta_today_notify_snooze
        ADD client_device NVARCHAR(2000) NULL;
    PRINT N'OK: client_device';
END
GO
