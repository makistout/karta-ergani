/* Κατάλογος πρωτοκόλλων χτυπημάτων κάρτας από portal Ergani (WorkCardSearch). */
IF OBJECT_ID(N'dbo.karta_ergani_protocol', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.karta_ergani_protocol (
        id BIGINT NOT NULL IDENTITY(1,1) CONSTRAINT PK_karta_ergani_protocol PRIMARY KEY CLUSTERED,
        store_id INT NOT NULL,
        employer_afm NVARCHAR(9) NOT NULL,
        branch_aa NVARCHAR(32) NOT NULL,
        submission_code NVARCHAR(64) NOT NULL CONSTRAINT DF_karta_ergani_protocol_code DEFAULT (N'WRKCardSE'),
        protocol NVARCHAR(128) NOT NULL,
        submit_at DATETIMEOFFSET(7) NULL,
        submit_date_text NVARCHAR(128) NULL,
        submission_status NVARCHAR(64) NULL,
        declaration_type NVARCHAR(256) NULL,
        overdue BIT NULL,
        source NVARCHAR(32) NOT NULL CONSTRAINT DF_karta_ergani_protocol_source DEFAULT (N'portal_excel'),
        synced_at DATETIMEOFFSET(7) NOT NULL CONSTRAINT DF_karta_ergani_protocol_synced DEFAULT (SYSDATETIMEOFFSET()),
        sync_run_id NVARCHAR(64) NULL,
        declaration_id BIGINT NULL,
        CONSTRAINT FK_karta_ergani_protocol_store FOREIGN KEY (store_id)
            REFERENCES dbo.karta_store_config (id) ON DELETE CASCADE,
        CONSTRAINT FK_karta_ergani_protocol_declaration FOREIGN KEY (declaration_id)
            REFERENCES dbo.karta_declaration (id),
        CONSTRAINT UQ_karta_ergani_protocol_store_protocol UNIQUE (store_id, protocol)
    );
    CREATE INDEX IX_karta_ergani_protocol_store_submit
        ON dbo.karta_ergani_protocol (store_id, submit_at DESC)
        INCLUDE (protocol, submission_status, declaration_id);
    CREATE INDEX IX_karta_ergani_protocol_employer_submit
        ON dbo.karta_ergani_protocol (employer_afm, branch_aa, submit_at DESC);
END
GO

IF COL_LENGTH(N'dbo.karta_store_config', N'protocol_last_sync_at') IS NULL
    ALTER TABLE dbo.karta_store_config ADD protocol_last_sync_at DATETIMEOFFSET(7) NULL;
GO
