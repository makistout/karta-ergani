IF COL_LENGTH(N'dbo.karta_billing_customer', N'representative') IS NULL
BEGIN
    ALTER TABLE dbo.karta_billing_customer ADD representative NVARCHAR(200) NULL;
    PRINT N'OK: billing customer representative';
END
GO
