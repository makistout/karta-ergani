/*
  Στοιχεία ταυτότητας ΑΠΔ:
  - ΑΜΕ εργοδότη ανά κατάστημα (e-ΕΦΚΑ, δεν έρχεται από Εργάνη)
  - ΑΜΚΑ και ΑΜΑ (AmIka) εργαζομένου (από EX_BASE_05)
*/

SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
GO

IF COL_LENGTH(N'dbo.karta_store_config', N'ame') IS NULL
BEGIN
    ALTER TABLE dbo.karta_store_config
        ADD ame NVARCHAR(20) NULL;
    PRINT N'OK: karta_store_config.ame';
END
GO

IF COL_LENGTH(N'dbo.karta_employee', N'amka') IS NULL
BEGIN
    ALTER TABLE dbo.karta_employee
        ADD amka NVARCHAR(11) NULL;
    PRINT N'OK: karta_employee.amka';
END
GO

IF COL_LENGTH(N'dbo.karta_employee', N'amika') IS NULL
BEGIN
    ALTER TABLE dbo.karta_employee
        ADD amika NVARCHAR(20) NULL;
    PRINT N'OK: karta_employee.amika';
END
GO
