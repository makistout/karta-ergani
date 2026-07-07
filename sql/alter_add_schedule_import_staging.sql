/*
  Migration: ενδιάμεσοι πίνακες εισαγωγής εβδομαδιαίου ωραρίου από Excel.
*/
SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
GO

IF OBJECT_ID(N'dbo.karta_schedule_import_batch', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.karta_schedule_import_batch (
        id BIGINT NOT NULL IDENTITY(1,1) CONSTRAINT PK_karta_schedule_import_batch PRIMARY KEY CLUSTERED,
        store_id INT NOT NULL,
        employer_afm NVARCHAR(9) NOT NULL,
        branch_aa NVARCHAR(32) NOT NULL,
        original_filename NVARCHAR(255) NULL,
        week_label NVARCHAR(128) NULL,
        status NVARCHAR(32) NOT NULL CONSTRAINT DF_karta_schedule_import_batch_status DEFAULT (N'preview'),
        created_by_user_id INT NULL,
        created_at DATETIMEOFFSET(7) NOT NULL CONSTRAINT DF_karta_schedule_import_batch_created DEFAULT (SYSDATETIMEOFFSET()),
        applied_at DATETIMEOFFSET(7) NULL,
        summary_json NVARCHAR(MAX) NULL
    );
    CREATE INDEX IX_karta_schedule_import_batch_store
        ON dbo.karta_schedule_import_batch (store_id, created_at DESC);
    PRINT N'OK: karta_schedule_import_batch';
END
GO

IF OBJECT_ID(N'dbo.karta_schedule_import_row', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.karta_schedule_import_row (
        id BIGINT NOT NULL IDENTITY(1,1) CONSTRAINT PK_karta_schedule_import_row PRIMARY KEY CLUSTERED,
        batch_id BIGINT NOT NULL,
        row_no INT NOT NULL,
        sheet_name NVARCHAR(64) NULL,
        work_date NVARCHAR(32) NOT NULL,
        employee_afm NVARCHAR(9) NOT NULL,
        eponymo NVARCHAR(128) NULL,
        onoma NVARCHAR(128) NULL,
        import_action NVARCHAR(16) NOT NULL,
        hour_from_1 NVARCHAR(16) NULL,
        hour_to_1 NVARCHAR(16) NULL,
        hour_from_2 NVARCHAR(16) NULL,
        hour_to_2 NVARCHAR(16) NULL,
        schedule_type NVARCHAR(16) NULL,
        change_kind NVARCHAR(16) NOT NULL,
        current_snapshot_json NVARCHAR(MAX) NULL,
        proposed_snapshot_json NVARCHAR(MAX) NULL,
        validation_errors_json NVARCHAR(MAX) NULL,
        apply_status NVARCHAR(16) NULL,
        apply_message NVARCHAR(500) NULL,
        ergani_protocol NVARCHAR(64) NULL,
        CONSTRAINT FK_karta_schedule_import_row_batch
            FOREIGN KEY (batch_id) REFERENCES dbo.karta_schedule_import_batch(id) ON DELETE CASCADE
    );
    CREATE INDEX IX_karta_schedule_import_row_batch
        ON dbo.karta_schedule_import_row (batch_id, work_date, employee_afm);
    PRINT N'OK: karta_schedule_import_row';
END
GO
