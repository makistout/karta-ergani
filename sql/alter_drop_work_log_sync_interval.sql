/* Αφαίρεση per-store διαστήματος auto-sync πραγματικής — αντικαθίσταται από server scheduler 10 λεπτά */
SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
GO

IF EXISTS (
    SELECT 1 FROM sys.default_constraints
    WHERE parent_object_id = OBJECT_ID(N'dbo.karta_store_config')
      AND name = N'DF_karta_store_wl_sync_interval'
)
BEGIN
    ALTER TABLE dbo.karta_store_config DROP CONSTRAINT DF_karta_store_wl_sync_interval;
    PRINT N'OK: dropped DF_karta_store_wl_sync_interval';
END
GO

IF COL_LENGTH(N'dbo.karta_store_config', N'work_log_sync_interval_minutes') IS NOT NULL
BEGIN
    ALTER TABLE dbo.karta_store_config DROP COLUMN work_log_sync_interval_minutes;
    PRINT N'OK: dropped work_log_sync_interval_minutes';
END
GO
