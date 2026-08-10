SET XACT_ABORT ON;
BEGIN TRANSACTION;

IF COL_LENGTH(N'dbo.karta_store_config', N'card_submission_mode') IS NULL
BEGIN
    ALTER TABLE dbo.karta_store_config ADD
        card_submission_mode NVARCHAR(16) NOT NULL
            CONSTRAINT DF_karta_store_card_submission_mode DEFAULT (N'erganios');
END;

IF COL_LENGTH(N'dbo.karta_store_config', N'listener_offline_seconds') IS NULL
BEGIN
    ALTER TABLE dbo.karta_store_config ADD
        listener_offline_seconds INT NOT NULL
            CONSTRAINT DF_karta_store_listener_offline_seconds DEFAULT (60);
END;

IF OBJECT_ID(N'dbo.CK_karta_store_card_submission_mode', N'C') IS NULL
BEGIN
    EXEC(N'ALTER TABLE dbo.karta_store_config ADD
        CONSTRAINT CK_karta_store_card_submission_mode
        CHECK (card_submission_mode IN (N''erganios'', N''listener''));');
END;

IF OBJECT_ID(N'dbo.CK_karta_store_listener_offline_seconds', N'C') IS NULL
BEGIN
    EXEC(N'ALTER TABLE dbo.karta_store_config ADD
        CONSTRAINT CK_karta_store_listener_offline_seconds
        CHECK (listener_offline_seconds BETWEEN 15 AND 600);');
END;

IF OBJECT_ID(N'dbo.karta_card_listener_device', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.karta_card_listener_device (
        id BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT PK_karta_card_listener_device PRIMARY KEY,
        store_id INT NOT NULL,
        device_id UNIQUEIDENTIFIER NOT NULL CONSTRAINT DF_karta_card_listener_device_id DEFAULT NEWID(),
        device_name NVARCHAR(200) NULL,
        agent_version NVARCHAR(32) NULL,
        credential_hash VARBINARY(32) NOT NULL,
        enabled BIT NOT NULL CONSTRAINT DF_karta_card_listener_enabled DEFAULT (1),
        paired_at DATETIMEOFFSET(7) NOT NULL CONSTRAINT DF_karta_card_listener_paired DEFAULT SYSDATETIMEOFFSET(),
        last_seen_at DATETIMEOFFSET(7) NULL,
        last_seen_ip NVARCHAR(45) NULL,
        revoked_at DATETIMEOFFSET(7) NULL,
        CONSTRAINT FK_karta_card_listener_store FOREIGN KEY (store_id)
            REFERENCES dbo.karta_store_config(id) ON DELETE CASCADE,
        CONSTRAINT UQ_karta_card_listener_device_id UNIQUE (device_id)
    );
    CREATE UNIQUE INDEX UX_karta_card_listener_one_active_per_store
        ON dbo.karta_card_listener_device(store_id)
        WHERE enabled = 1 AND revoked_at IS NULL;
    CREATE INDEX IX_karta_card_listener_store_seen
        ON dbo.karta_card_listener_device(store_id, enabled, last_seen_at);
END;

IF OBJECT_ID(N'dbo.karta_card_listener_job', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.karta_card_listener_job (
        id BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT PK_karta_card_listener_job PRIMARY KEY,
        job_uuid UNIQUEIDENTIFIER NOT NULL CONSTRAINT DF_karta_card_listener_job_uuid DEFAULT NEWID(),
        store_id INT NOT NULL,
        device_id UNIQUEIDENTIFIER NULL,
        status NVARCHAR(32) NOT NULL CONSTRAINT DF_karta_card_listener_job_status DEFAULT (N'queued'),
        idempotency_key NVARCHAR(128) NOT NULL,
        employee_afm NVARCHAR(9) NOT NULL,
        f_type NVARCHAR(16) NOT NULL,
        reference_date NVARCHAR(10) NOT NULL,
        event_at DATETIMEOFFSET(7) NOT NULL,
        payload_json NVARCHAR(MAX) NOT NULL,
        ergani_api_base_url NVARCHAR(500) NOT NULL,
        available_at DATETIMEOFFSET(7) NOT NULL CONSTRAINT DF_karta_card_listener_job_available DEFAULT SYSDATETIMEOFFSET(),
        fallback_deadline DATETIMEOFFSET(7) NOT NULL,
        leased_at DATETIMEOFFSET(7) NULL,
        lease_expires_at DATETIMEOFFSET(7) NULL,
        completed_at DATETIMEOFFSET(7) NULL,
        fallback_started_at DATETIMEOFFSET(7) NULL,
        attempt_count INT NOT NULL CONSTRAINT DF_karta_card_listener_job_attempt_count DEFAULT (0),
        upstream_http_status INT NULL,
        protocol NVARCHAR(128) NULL,
        ergani_submission_id NVARCHAR(64) NULL,
        submit_date_text NVARCHAR(128) NULL,
        result_json NVARCHAR(MAX) NULL,
        error_code NVARCHAR(64) NULL,
        error_summary NVARCHAR(1000) NULL,
        declaration_id BIGINT NULL,
        submission_ip NVARCHAR(45) NULL,
        executor_instance NVARCHAR(200) NULL,
        created_at DATETIMEOFFSET(7) NOT NULL CONSTRAINT DF_karta_card_listener_job_created DEFAULT SYSDATETIMEOFFSET(),
        updated_at DATETIMEOFFSET(7) NOT NULL CONSTRAINT DF_karta_card_listener_job_updated DEFAULT SYSDATETIMEOFFSET(),
        CONSTRAINT FK_karta_card_listener_job_store FOREIGN KEY (store_id)
            REFERENCES dbo.karta_store_config(id) ON DELETE CASCADE,
        CONSTRAINT FK_karta_card_listener_job_declaration FOREIGN KEY (declaration_id)
            REFERENCES dbo.karta_declaration(id),
        CONSTRAINT UQ_karta_card_listener_job_uuid UNIQUE (job_uuid),
        CONSTRAINT UQ_karta_card_listener_job_idempotency UNIQUE (idempotency_key),
        CONSTRAINT CK_karta_card_listener_job_type CHECK (f_type IN (N'0', N'1')),
        CONSTRAINT CK_karta_card_listener_job_status CHECK (status IN (
            N'queued', N'leased', N'submitting', N'succeeded', N'failed', N'needs_review',
            N'cancelled_for_fallback', N'fallback_submitting', N'fallback_succeeded', N'fallback_failed'
        ))
    );
    CREATE INDEX IX_karta_card_listener_job_poll
        ON dbo.karta_card_listener_job(store_id, status, available_at, created_at)
        INCLUDE (job_uuid, fallback_deadline, lease_expires_at);
    CREATE INDEX IX_karta_card_listener_job_status_deadline
        ON dbo.karta_card_listener_job(status, fallback_deadline);
    CREATE INDEX IX_karta_card_listener_job_employee
        ON dbo.karta_card_listener_job(store_id, employee_afm, reference_date, f_type);
END;

IF OBJECT_ID(N'dbo.karta_card_listener_attempt', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.karta_card_listener_attempt (
        id BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT PK_karta_card_listener_attempt PRIMARY KEY,
        job_id BIGINT NOT NULL,
        device_id UNIQUEIDENTIFIER NULL,
        execution_source NVARCHAR(16) NOT NULL,
        attempt_number INT NOT NULL,
        started_at DATETIMEOFFSET(7) NOT NULL CONSTRAINT DF_karta_card_listener_attempt_started DEFAULT SYSDATETIMEOFFSET(),
        finished_at DATETIMEOFFSET(7) NULL,
        http_status INT NULL,
        success BIT NULL,
        error_code NVARCHAR(64) NULL,
        error_summary NVARCHAR(1000) NULL,
        submission_ip NVARCHAR(45) NULL,
        executor_instance NVARCHAR(200) NULL,
        CONSTRAINT FK_karta_card_listener_attempt_job FOREIGN KEY (job_id)
            REFERENCES dbo.karta_card_listener_job(id) ON DELETE CASCADE,
        CONSTRAINT CK_karta_card_listener_attempt_source
            CHECK (execution_source IN (N'listener', N'erganios')),
        CONSTRAINT UQ_karta_card_listener_attempt_number
            UNIQUE (job_id, execution_source, attempt_number)
    );
    CREATE INDEX IX_karta_card_listener_attempt_job
        ON dbo.karta_card_listener_attempt(job_id, started_at DESC);
END;

COMMIT TRANSACTION;
GO
