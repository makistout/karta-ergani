/*
  Migration: πραγματική απασχόληση (EX_BASE_07)
*/
SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
GO

IF OBJECT_ID(N'dbo.karta_work_log', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.karta_work_log (
        id BIGINT NOT NULL IDENTITY(1,1) CONSTRAINT PK_karta_work_log PRIMARY KEY CLUSTERED,
        employer_afm NVARCHAR(9) NOT NULL,
        branch_aa NVARCHAR(32) NOT NULL,
        work_date NVARCHAR(32) NOT NULL,
        employee_afm NVARCHAR(9) NULL,
        hour_from NVARCHAR(16) NULL,
        hour_to NVARCHAR(16) NULL,
        source_aa NVARCHAR(32) NULL,
        is_end_date_different BIT NULL,
        synced_at DATETIMEOFFSET(7) NOT NULL CONSTRAINT DF_karta_work_log_synced DEFAULT (SYSDATETIMEOFFSET())
    );
    CREATE INDEX IX_karta_work_log_lookup
        ON dbo.karta_work_log (employer_afm, branch_aa, work_date);
    PRINT N'OK: karta_work_log';
END
GO
