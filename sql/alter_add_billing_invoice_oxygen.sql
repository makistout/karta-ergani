IF COL_LENGTH(N'dbo.karta_billing_document', N'mark') IS NULL
BEGIN
    ALTER TABLE dbo.karta_billing_document ADD
        invoice_type NVARCHAR(8) NULL,
        mark NVARCHAR(64) NULL,
        uid NVARCHAR(80) NULL,
        icode NVARCHAR(64) NULL,
        authentication_code NVARCHAR(128) NULL,
        oxygen_id NVARCHAR(64) NULL,
        qr_url NVARCHAR(500) NULL,
        oxygen_error NVARCHAR(1000) NULL;
    PRINT N'OK: billing document oxygen columns';
END
GO

IF COL_LENGTH(N'dbo.karta_billing_subscription', N'document_id') IS NULL
BEGIN
    ALTER TABLE dbo.karta_billing_subscription ADD document_id INT NULL;
    PRINT N'OK: billing subscription document_id';
END
GO

IF COL_LENGTH(N'dbo.karta_billing_document', N'related_document_id') IS NULL
BEGIN
    ALTER TABLE dbo.karta_billing_document ADD related_document_id INT NULL;
    PRINT N'OK: billing document related_document_id';
END
GO
