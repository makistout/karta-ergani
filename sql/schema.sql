/*
  Βάση MSSQL: ergani-karta
  Αποκλειστικά pyodbc — χωρίς SQLAlchemy.
  Πρόθεμα πινάκων: karta_
*/
SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
GO

IF OBJECT_ID(N'dbo.karta_store_config', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.karta_store_config (
        id INT NOT NULL IDENTITY(1,1) CONSTRAINT PK_karta_store_config PRIMARY KEY CLUSTERED,
        name NVARCHAR(200) NOT NULL,
        username NVARCHAR(128) NOT NULL,
        password NVARCHAR(256) NOT NULL,
        usertype NVARCHAR(8) NOT NULL CONSTRAINT DF_karta_store_usertype DEFAULT (N'02'),
        web_username NVARCHAR(128) NULL,
        web_password NVARCHAR(256) NULL,
        employer_afm NVARCHAR(9) NOT NULL,
        branch_aa NVARCHAR(32) NOT NULL CONSTRAINT DF_karta_store_branch DEFAULT (N'0'),
        ergani_env NVARCHAR(16) NOT NULL CONSTRAINT DF_karta_store_ergani_env DEFAULT (N'production'),
        sepe_code NVARCHAR(64) NULL,
        sepe_desc NVARCHAR(500) NULL,
        oaed_code NVARCHAR(64) NULL,
        oaed_desc NVARCHAR(500) NULL,
        kad_code NVARCHAR(32) NULL,
        kad_desc NVARCHAR(500) NULL,
        kallikratis_code NVARCHAR(16) NULL,
        kallikratis_desc NVARCHAR(500) NULL,
        updated_at DATETIMEOFFSET(7) NOT NULL CONSTRAINT DF_karta_store_updated DEFAULT (SYSDATETIMEOFFSET()),
        last_sync_at DATETIMEOFFSET(7) NULL
    );
    CREATE INDEX IX_karta_store_employer ON dbo.karta_store_config (employer_afm, branch_aa);
END
GO

IF OBJECT_ID(N'dbo.karta_employer', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.karta_employer (
        id BIGINT NOT NULL IDENTITY(1,1) CONSTRAINT PK_karta_employer PRIMARY KEY CLUSTERED,
        afm NVARCHAR(9) NOT NULL,
        eponimia NVARCHAR(500) NULL,
        updated_at DATETIMEOFFSET(7) NOT NULL CONSTRAINT DF_karta_employer_updated DEFAULT (SYSDATETIMEOFFSET()),
        CONSTRAINT UQ_karta_employer_afm UNIQUE (afm)
    );
END
GO

IF OBJECT_ID(N'dbo.karta_parartima', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.karta_parartima (
        id BIGINT NOT NULL IDENTITY(1,1) CONSTRAINT PK_karta_parartima PRIMARY KEY CLUSTERED,
        employer_id BIGINT NOT NULL,
        code_aa NVARCHAR(32) NOT NULL,
        description NVARCHAR(500) NULL,
        updated_at DATETIMEOFFSET(7) NOT NULL CONSTRAINT DF_karta_parartima_updated DEFAULT (SYSDATETIMEOFFSET()),
        CONSTRAINT FK_karta_parartima_employer FOREIGN KEY (employer_id) REFERENCES dbo.karta_employer (id),
        CONSTRAINT UQ_karta_parartima_emp_aa UNIQUE (employer_id, code_aa)
    );
END
GO

IF OBJECT_ID(N'dbo.karta_employee', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.karta_employee (
        id BIGINT NOT NULL IDENTITY(1,1) CONSTRAINT PK_karta_employee PRIMARY KEY CLUSTERED,
        afm NVARCHAR(9) NOT NULL,
        eponymo NVARCHAR(200) NULL,
        onoma NVARCHAR(200) NULL,
        flex_arrival_minutes INT NULL,
        updated_at DATETIMEOFFSET(7) NOT NULL CONSTRAINT DF_karta_employee_updated DEFAULT (SYSDATETIMEOFFSET()),
        CONSTRAINT UQ_karta_employee_afm UNIQUE (afm)
    );
    CREATE INDEX IX_karta_employee_names ON dbo.karta_employee (eponymo, onoma);
END
GO

IF OBJECT_ID(N'dbo.karta_employment', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.karta_employment (
        id BIGINT NOT NULL IDENTITY(1,1) CONSTRAINT PK_karta_employment PRIMARY KEY CLUSTERED,
        employer_id BIGINT NOT NULL,
        employee_id BIGINT NOT NULL,
        parartima_id BIGINT NULL,
        active BIT NOT NULL CONSTRAINT DF_karta_employment_active DEFAULT (1),
        updated_at DATETIMEOFFSET(7) NOT NULL CONSTRAINT DF_karta_employment_updated DEFAULT (SYSDATETIMEOFFSET()),
        CONSTRAINT FK_karta_employment_employer FOREIGN KEY (employer_id) REFERENCES dbo.karta_employer (id),
        CONSTRAINT FK_karta_employment_employee FOREIGN KEY (employee_id) REFERENCES dbo.karta_employee (id),
        CONSTRAINT FK_karta_employment_parartima FOREIGN KEY (parartima_id) REFERENCES dbo.karta_parartima (id)
    );
    CREATE INDEX IX_karta_employment_employer ON dbo.karta_employment (employer_id);
    CREATE INDEX IX_karta_employment_employee ON dbo.karta_employment (employee_id);
END
GO

IF OBJECT_ID(N'dbo.karta_schedule', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.karta_schedule (
        id BIGINT NOT NULL IDENTITY(1,1) CONSTRAINT PK_karta_schedule PRIMARY KEY CLUSTERED,
        employer_afm NVARCHAR(9) NOT NULL,
        branch_aa NVARCHAR(32) NOT NULL,
        work_date NVARCHAR(32) NOT NULL,
        employee_afm NVARCHAR(9) NULL,
        hour_from NVARCHAR(16) NULL,
        hour_to NVARCHAR(16) NULL,
        shift_type NVARCHAR(64) NULL,
        break_minutes INT NULL,
        break_in_work INT NULL,
        extra NVARCHAR(500) NULL,
        source_aa NVARCHAR(32) NULL,
        synced_at DATETIMEOFFSET(7) NOT NULL CONSTRAINT DF_karta_schedule_synced DEFAULT (SYSDATETIMEOFFSET())
    );
    CREATE INDEX IX_karta_schedule_lookup ON dbo.karta_schedule (employer_afm, branch_aa, work_date);
    CREATE INDEX IX_karta_schedule_emp ON dbo.karta_schedule (employee_afm, work_date);
END
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
    CREATE INDEX IX_karta_work_log_lookup ON dbo.karta_work_log (employer_afm, branch_aa, work_date);
END
GO

IF OBJECT_ID(N'dbo.karta_declaration', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.karta_declaration (
        id BIGINT NOT NULL IDENTITY(1,1) CONSTRAINT PK_karta_declaration PRIMARY KEY CLUSTERED,
        submission_code NVARCHAR(64) NOT NULL,
        direction NVARCHAR(32) NOT NULL,
        employer_afm NVARCHAR(9) NULL,
        protocol NVARCHAR(128) NULL,
        submit_date_text NVARCHAR(128) NULL,
        ergani_submission_id NVARCHAR(32) NULL,
        http_status INT NOT NULL,
        success BIT NOT NULL CONSTRAINT DF_karta_declaration_success DEFAULT (0),
        request_json NVARCHAR(MAX) NULL,
        response_json NVARCHAR(MAX) NULL,
        created_at DATETIMEOFFSET(7) NOT NULL CONSTRAINT DF_karta_declaration_created DEFAULT (SYSDATETIMEOFFSET())
    );
    CREATE INDEX IX_karta_declaration_code_created ON dbo.karta_declaration (submission_code, created_at DESC);
END
GO

IF OBJECT_ID(N'dbo.karta_card_event', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.karta_card_event (
        id BIGINT NOT NULL IDENTITY(1,1) CONSTRAINT PK_karta_card_event PRIMARY KEY CLUSTERED,
        declaration_id BIGINT NOT NULL,
        employee_id BIGINT NULL,
        f_afm_ergodoti NVARCHAR(9) NULL,
        f_aa NVARCHAR(32) NULL,
        f_comments NVARCHAR(MAX) NULL,
        f_afm NVARCHAR(9) NULL,
        f_eponymo NVARCHAR(200) NULL,
        f_onoma NVARCHAR(200) NULL,
        f_type NVARCHAR(16) NULL,
        f_reference_date NVARCHAR(32) NULL,
        f_date NVARCHAR(64) NULL,
        f_aitiologia NVARCHAR(MAX) NULL,
        CONSTRAINT FK_karta_card_event_declaration FOREIGN KEY (declaration_id)
            REFERENCES dbo.karta_declaration (id) ON DELETE CASCADE,
        CONSTRAINT FK_karta_card_event_employee FOREIGN KEY (employee_id) REFERENCES dbo.karta_employee (id)
    );
    CREATE INDEX IX_karta_card_event_declaration ON dbo.karta_card_event (declaration_id);
    CREATE INDEX IX_karta_card_event_afm_date_type ON dbo.karta_card_event (f_afm, f_reference_date, f_type);
END
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
END
GO
