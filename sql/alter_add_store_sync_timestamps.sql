/* Τελευταίος συγχρονισμός ωραρίου / πραγματικής + διάστημα auto-sync πραγματικής (λεπτά) */
SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
GO

IF COL_LENGTH(N'dbo.karta_store_config', N'schedule_last_sync_at') IS NULL
BEGIN
    ALTER TABLE dbo.karta_store_config
        ADD schedule_last_sync_at DATETIMEOFFSET(7) NULL;
    PRINT N'OK: schedule_last_sync_at';
END
GO

IF COL_LENGTH(N'dbo.karta_store_config', N'work_log_last_sync_at') IS NULL
BEGIN
    ALTER TABLE dbo.karta_store_config
        ADD work_log_last_sync_at DATETIMEOFFSET(7) NULL;
    PRINT N'OK: work_log_last_sync_at';
END
GO

IF COL_LENGTH(N'dbo.karta_store_config', N'work_log_sync_interval_minutes') IS NULL
BEGIN
    ALTER TABLE dbo.karta_store_config
        ADD work_log_sync_interval_minutes INT NOT NULL
            CONSTRAINT DF_karta_store_wl_sync_interval DEFAULT (30);
    PRINT N'OK: work_log_sync_interval_minutes';
END
GO
