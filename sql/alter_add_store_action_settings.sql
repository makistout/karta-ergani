/*
  Ρυθμίσεις αυτόματων ενεργειών ανά κατάστημα.
  auto_close_prev_day_*: κλείσιμο ανοιχτών καρτών μόνο για την προηγούμενη ημέρα.
*/

IF COL_LENGTH(N'dbo.karta_store_config', N'auto_close_prev_day_enabled') IS NULL
BEGIN
    ALTER TABLE dbo.karta_store_config
        ADD auto_close_prev_day_enabled BIT NOT NULL
            CONSTRAINT DF_karta_store_auto_close_prev_day_enabled DEFAULT (0);
    PRINT N'OK: auto_close_prev_day_enabled';
END
GO

IF COL_LENGTH(N'dbo.karta_store_config', N'auto_close_prev_day_time') IS NULL
BEGIN
    ALTER TABLE dbo.karta_store_config
        ADD auto_close_prev_day_time NVARCHAR(5) NOT NULL
            CONSTRAINT DF_karta_store_auto_close_prev_day_time DEFAULT (N'00:30');
    PRINT N'OK: auto_close_prev_day_time';
END
GO

IF COL_LENGTH(N'dbo.karta_store_config', N'auto_close_prev_day_last_run_date') IS NULL
BEGIN
    ALTER TABLE dbo.karta_store_config
        ADD auto_close_prev_day_last_run_date NVARCHAR(10) NULL;
    PRINT N'OK: auto_close_prev_day_last_run_date';
END
GO
