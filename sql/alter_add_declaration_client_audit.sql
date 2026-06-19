/*
  IP και στοιχεία συσκευής για υποβολές κάρτας από erganiOS.
*/
SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
GO

IF COL_LENGTH(N'dbo.karta_declaration', N'client_ip') IS NULL
BEGIN
    ALTER TABLE dbo.karta_declaration
        ADD client_ip NVARCHAR(45) NULL;
    PRINT N'OK: client_ip';
END
GO

IF COL_LENGTH(N'dbo.karta_declaration', N'client_device') IS NULL
BEGIN
    ALTER TABLE dbo.karta_declaration
        ADD client_device NVARCHAR(2000) NULL;
    PRINT N'OK: client_device';
END
GO
