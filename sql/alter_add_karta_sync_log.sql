/*
  Migration: καταγραφή συγχρονισμών στη βάση (runs + γραμμές log)
*/
SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
GO

IF OBJECT_ID(N'dbo.karta_sync_run', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.karta_sync_run (
        id BIGINT NOT NULL IDENTITY(1,1) CONSTRAINT PK_karta_sync_run PRIMARY KEY CLUSTERED,
        run_id NVARCHAR(36) NOT NULL,
        store_id INT NULL,
        operation NVARCHAR(64) NOT NULL,
        status NVARCHAR(16) NOT NULL CONSTRAINT DF_karta_sync_run_status DEFAULT (N'running'),
        message NVARCHAR(500) NULL,
        step INT NULL,
        total INT NULL,
        result_json NVARCHAR(MAX) NULL,
        started_at DATETIMEOFFSET(7) NOT NULL CONSTRAINT DF_karta_sync_run_started DEFAULT (SYSDATETIMEOFFSET()),
        finished_at DATETIMEOFFSET(7) NULL,
        CONSTRAINT UQ_karta_sync_run_run_id UNIQUE (run_id)
    );
    CREATE INDEX IX_karta_sync_run_store_started
        ON dbo.karta_sync_run (store_id, started_at DESC);
    PRINT N'OK: karta_sync_run';
END
GO

IF OBJECT_ID(N'dbo.karta_sync_log', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.karta_sync_log (
        id BIGINT NOT NULL IDENTITY(1,1) CONSTRAINT PK_karta_sync_log PRIMARY KEY CLUSTERED,
        run_id NVARCHAR(36) NOT NULL,
        seq INT NOT NULL,
        level NVARCHAR(8) NOT NULL,
        message NVARCHAR(MAX) NOT NULL,
        fields_json NVARCHAR(MAX) NULL,
        created_at DATETIMEOFFSET(7) NOT NULL CONSTRAINT DF_karta_sync_log_created DEFAULT (SYSDATETIMEOFFSET())
    );
    CREATE INDEX IX_karta_sync_log_run_seq ON dbo.karta_sync_log (run_id, seq);
    PRINT N'OK: karta_sync_log';
END
GO
