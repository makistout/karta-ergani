-- QR ψηφιακής οργάνωσης χρόνου εργασίας ανά σχέση εργαζόμενου-καταστήματος
IF COL_LENGTH(N'dbo.karta_employment', N'work_time_qr_data_url') IS NULL
BEGIN
    ALTER TABLE dbo.karta_employment
        ADD work_time_qr_data_url NVARCHAR(MAX) NULL;
    PRINT N'OK: karta_employment.work_time_qr_data_url';
END
GO

IF COL_LENGTH(N'dbo.karta_employment', N'work_time_qr_synced_at') IS NULL
BEGIN
    ALTER TABLE dbo.karta_employment
        ADD work_time_qr_synced_at DATETIMEOFFSET(7) NULL;
    PRINT N'OK: karta_employment.work_time_qr_synced_at';
END
GO
