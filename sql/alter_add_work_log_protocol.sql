/* Πρωτόκολλα εισόδου/εξόδου πάνω στην πραγματική (karta_work_log). */
IF COL_LENGTH(N'dbo.karta_work_log', N'protocol_from') IS NULL
    ALTER TABLE dbo.karta_work_log ADD protocol_from NVARCHAR(128) NULL;
GO

IF COL_LENGTH(N'dbo.karta_work_log', N'protocol_to') IS NULL
    ALTER TABLE dbo.karta_work_log ADD protocol_to NVARCHAR(128) NULL;
GO
