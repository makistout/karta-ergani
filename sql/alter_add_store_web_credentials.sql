/*
  Migration: διαπιστευτήρια web portal (ξεχωριστά από admin/API EFKA)
*/
SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
GO

IF COL_LENGTH(N'dbo.karta_store_config', N'web_username') IS NULL
BEGIN
    ALTER TABLE dbo.karta_store_config ADD web_username NVARCHAR(128) NULL;
    PRINT N'OK: web_username';
END
GO

IF COL_LENGTH(N'dbo.karta_store_config', N'web_password') IS NULL
BEGIN
    ALTER TABLE dbo.karta_store_config ADD web_password NVARCHAR(256) NULL;
    PRINT N'OK: web_password';
END
GO
