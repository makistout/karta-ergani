/*
  Ανεξάρτητο audit trail ενεργειών χρήστη/API.
  Δεν σχετίζεται με τα logs συγχρονισμού καταστημάτων.
*/
SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
GO

IF OBJECT_ID(N'dbo.karta_audit_log', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.karta_audit_log (
        id BIGINT NOT NULL IDENTITY(1,1) CONSTRAINT PK_karta_audit_log PRIMARY KEY CLUSTERED,
        created_at DATETIMEOFFSET(7) NOT NULL CONSTRAINT DF_karta_audit_created DEFAULT (SYSDATETIMEOFFSET()),
        actor_type NVARCHAR(32) NULL,
        actor_name NVARCHAR(128) NULL,
        office_user NVARCHAR(128) NULL,
        store_id INT NULL,
        employer_afm NVARCHAR(9) NULL,
        branch_aa NVARCHAR(32) NULL,
        action NVARCHAR(128) NOT NULL,
        entity_type NVARCHAR(64) NULL,
        entity_id NVARCHAR(128) NULL,
        success BIT NULL,
        http_status INT NULL,
        request_method NVARCHAR(16) NULL,
        request_path NVARCHAR(512) NULL,
        endpoint NVARCHAR(256) NULL,
        client_ip NVARCHAR(45) NULL,
        client_device NVARCHAR(2000) NULL,
        details_json NVARCHAR(MAX) NULL
    );
    CREATE INDEX IX_karta_audit_created ON dbo.karta_audit_log (created_at DESC);
    CREATE INDEX IX_karta_audit_store_created ON dbo.karta_audit_log (store_id, created_at DESC);
    CREATE INDEX IX_karta_audit_action_created ON dbo.karta_audit_log (action, created_at DESC);
    PRINT N'OK: karta_audit_log';
END
GO
