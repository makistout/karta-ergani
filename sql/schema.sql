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
        last_sync_at DATETIMEOFFSET(7) NULL,
        schedule_last_sync_at DATETIMEOFFSET(7) NULL,
        work_log_last_sync_at DATETIMEOFFSET(7) NULL,
        auto_close_prev_day_enabled BIT NOT NULL CONSTRAINT DF_karta_store_auto_close_prev_day_enabled DEFAULT (0),
        auto_close_prev_day_time NVARCHAR(5) NOT NULL CONSTRAINT DF_karta_store_auto_close_prev_day_time DEFAULT (N'00:30'),
        auto_close_prev_day_last_run_date NVARCHAR(10) NULL,
        sunday_rest_transfer_enabled BIT NOT NULL CONSTRAINT DF_karta_store_sunday_rest_transfer_enabled DEFAULT (0),
        uneven_distribution_enabled BIT NOT NULL CONSTRAINT DF_karta_store_uneven_distribution_enabled DEFAULT (0),
        card_submission_mode NVARCHAR(16) NOT NULL CONSTRAINT DF_karta_store_card_submission_mode DEFAULT (N'erganios'),
        listener_offline_seconds INT NOT NULL CONSTRAINT DF_karta_store_listener_offline_seconds DEFAULT (60),
        CONSTRAINT CK_karta_store_card_submission_mode CHECK (card_submission_mode IN (N'erganios', N'listener')),
        CONSTRAINT CK_karta_store_listener_offline_seconds CHECK (listener_offline_seconds BETWEEN 15 AND 600)
    );
    CREATE INDEX IX_karta_store_employer ON dbo.karta_store_config (employer_afm, branch_aa);
END
GO

-- See also alter_add_apologistic_snapshots.sql.
IF OBJECT_ID(N'dbo.karta_apologistic_run', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.karta_apologistic_run (
        id BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT PK_karta_apologistic_run PRIMARY KEY,
        store_id INT NOT NULL, employer_afm NVARCHAR(9) NOT NULL, branch_aa NVARCHAR(32) NOT NULL,
        week_from DATE NOT NULL, week_to DATE NOT NULL, status NVARCHAR(24) NOT NULL DEFAULT N'draft',
        calculation_version NVARCHAR(40) NOT NULL, generated_report_json NVARCHAR(MAX) NULL,
        effective_report_json NVARCHAR(MAX) NULL, error_summary NVARCHAR(2000) NULL,
        started_at DATETIMEOFFSET(7) NULL, completed_at DATETIMEOFFSET(7) NULL,
        created_at DATETIMEOFFSET(7) NOT NULL DEFAULT SYSDATETIMEOFFSET(),
        updated_at DATETIMEOFFSET(7) NOT NULL DEFAULT SYSDATETIMEOFFSET(),
        CONSTRAINT FK_karta_apologistic_run_store FOREIGN KEY (store_id) REFERENCES dbo.karta_store_config(id) ON DELETE CASCADE,
        CONSTRAINT UQ_karta_apologistic_run_store_week UNIQUE (store_id, week_from)
    );
    CREATE INDEX IX_karta_apologistic_run_week ON dbo.karta_apologistic_run(week_from,status,store_id);
END
GO

IF OBJECT_ID(N'dbo.karta_apologistic_day', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.karta_apologistic_day (
        id BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT PK_karta_apologistic_day PRIMARY KEY,
        run_id BIGINT NOT NULL, store_id INT NOT NULL, employee_afm NVARCHAR(9) NOT NULL, work_date DATE NOT NULL,
        generated_json NVARCHAR(MAX) NOT NULL, override_json NVARCHAR(MAX) NULL, effective_json NVARCHAR(MAX) NOT NULL,
        review_status NVARCHAR(24) NOT NULL DEFAULT N'draft', override_reason NVARCHAR(1000) NULL,
        updated_by NVARCHAR(128) NULL, override_updated_at DATETIMEOFFSET(7) NULL,
        generated_at DATETIMEOFFSET(7) NOT NULL DEFAULT SYSDATETIMEOFFSET(),
        updated_at DATETIMEOFFSET(7) NOT NULL DEFAULT SYSDATETIMEOFFSET(),
        CONSTRAINT FK_karta_apologistic_day_run FOREIGN KEY (run_id) REFERENCES dbo.karta_apologistic_run(id) ON DELETE CASCADE,
        CONSTRAINT FK_karta_apologistic_day_store FOREIGN KEY (store_id) REFERENCES dbo.karta_store_config(id),
        CONSTRAINT UQ_karta_apologistic_day_key UNIQUE (run_id,employee_afm,work_date)
    );
    CREATE INDEX IX_karta_apologistic_day_store_date ON dbo.karta_apologistic_day(store_id,work_date,employee_afm);
END
GO

IF OBJECT_ID(N'dbo.karta_apologistic_change', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.karta_apologistic_change (
        id BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT PK_karta_apologistic_change PRIMARY KEY,
        day_id BIGINT NOT NULL, field_name NVARCHAR(64) NOT NULL,
        old_value NVARCHAR(2000) NULL, new_value NVARCHAR(2000) NULL,
        changed_by NVARCHAR(128) NULL,
        changed_at DATETIMEOFFSET(7) NOT NULL DEFAULT SYSDATETIMEOFFSET(),
        CONSTRAINT FK_karta_apologistic_change_day FOREIGN KEY (day_id) REFERENCES dbo.karta_apologistic_day(id) ON DELETE CASCADE
    );
    CREATE INDEX IX_karta_apologistic_change_day_field ON dbo.karta_apologistic_change(day_id,field_name,changed_at DESC);
END
GO

IF OBJECT_ID(N'dbo.karta_apologistic_submit', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.karta_apologistic_submit (
        id BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT PK_karta_apologistic_submit PRIMARY KEY,
        day_id BIGINT NOT NULL,
        submission_code NVARCHAR(32) NOT NULL,
        declaration_id BIGINT NULL,
        proposed_at_submit NVARCHAR(64) NULL,
        segment_reference_date DATE NULL,
        protocol NVARCHAR(64) NULL,
        ergani_submission_id NVARCHAR(32) NULL,
        submit_date_text NVARCHAR(64) NULL,
        success BIT NOT NULL CONSTRAINT DF_karta_apologistic_submit_success DEFAULT (0),
        submitted_by NVARCHAR(128) NULL,
        submitted_at DATETIMEOFFSET(7) NOT NULL CONSTRAINT DF_karta_apologistic_submit_at DEFAULT SYSDATETIMEOFFSET(),
        CONSTRAINT FK_karta_apologistic_submit_day FOREIGN KEY (day_id) REFERENCES dbo.karta_apologistic_day(id) ON DELETE CASCADE,
        CONSTRAINT FK_karta_apologistic_submit_declaration FOREIGN KEY (declaration_id) REFERENCES dbo.karta_declaration(id)
    );
    CREATE INDEX IX_karta_apologistic_submit_day_code ON dbo.karta_apologistic_submit(day_id, submission_code, segment_reference_date, submitted_at DESC);
END
GO

IF OBJECT_ID(N'dbo.karta_apologistic_rest_obligation', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.karta_apologistic_rest_obligation (
        id BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT PK_karta_apologistic_rest_obligation PRIMARY KEY,
        store_id INT NOT NULL, employee_afm NVARCHAR(9) NOT NULL,
        source_run_id BIGINT NULL, source_work_date DATE NOT NULL,
        source_actual_minutes INT NOT NULL, source_punch_days INT NOT NULL,
        target_week_from DATE NOT NULL, target_week_to DATE NOT NULL,
        status NVARCHAR(24) NOT NULL DEFAULT N'pending', resolved_work_date DATE NULL,
        resolved_by NVARCHAR(128) NULL, resolution_note NVARCHAR(1000) NULL,
        resolved_at DATETIMEOFFSET(7) NULL,
        created_at DATETIMEOFFSET(7) NOT NULL DEFAULT SYSDATETIMEOFFSET(),
        updated_at DATETIMEOFFSET(7) NOT NULL DEFAULT SYSDATETIMEOFFSET(),
        CONSTRAINT FK_karta_apologistic_rest_store FOREIGN KEY (store_id) REFERENCES dbo.karta_store_config(id) ON DELETE CASCADE,
        CONSTRAINT FK_karta_apologistic_rest_run FOREIGN KEY (source_run_id) REFERENCES dbo.karta_apologistic_run(id),
        CONSTRAINT UQ_karta_apologistic_rest_source UNIQUE (store_id,employee_afm,source_work_date)
    );
    CREATE INDEX IX_karta_apologistic_rest_target ON dbo.karta_apologistic_rest_obligation(store_id,target_week_from,status,employee_afm);
END
GO

IF OBJECT_ID(N'dbo.karta_role', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.karta_role (
        code NVARCHAR(64) NOT NULL CONSTRAINT PK_karta_role PRIMARY KEY CLUSTERED,
        name NVARCHAR(128) NOT NULL,
        description NVARCHAR(500) NULL,
        created_at DATETIMEOFFSET(7) NOT NULL CONSTRAINT DF_karta_role_created DEFAULT (SYSDATETIMEOFFSET()),
        updated_at DATETIMEOFFSET(7) NOT NULL CONSTRAINT DF_karta_role_updated DEFAULT (SYSDATETIMEOFFSET())
    );
END
GO

IF OBJECT_ID(N'dbo.karta_permission', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.karta_permission (
        code NVARCHAR(128) NOT NULL CONSTRAINT PK_karta_permission PRIMARY KEY CLUSTERED,
        name NVARCHAR(200) NOT NULL,
        description NVARCHAR(500) NULL,
        created_at DATETIMEOFFSET(7) NOT NULL CONSTRAINT DF_karta_permission_created DEFAULT (SYSDATETIMEOFFSET()),
        updated_at DATETIMEOFFSET(7) NOT NULL CONSTRAINT DF_karta_permission_updated DEFAULT (SYSDATETIMEOFFSET())
    );
END
GO

IF OBJECT_ID(N'dbo.karta_user', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.karta_user (
        id INT NOT NULL IDENTITY(1,1) CONSTRAINT PK_karta_user PRIMARY KEY CLUSTERED,
        username NVARCHAR(128) NOT NULL,
        email NVARCHAR(255) NULL,
        password_hash NVARCHAR(512) NOT NULL,
        full_name NVARCHAR(200) NULL,
        is_active BIT NOT NULL CONSTRAINT DF_karta_user_active DEFAULT (1),
        is_super_admin BIT NOT NULL CONSTRAINT DF_karta_user_super DEFAULT (0),
        email_verified_at DATETIMEOFFSET(7) NULL,
        email_verification_token_hash NVARCHAR(128) NULL,
        email_verification_sent_at DATETIMEOFFSET(7) NULL,
        email_verification_expires_at DATETIMEOFFSET(7) NULL,
        created_at DATETIMEOFFSET(7) NOT NULL CONSTRAINT DF_karta_user_created DEFAULT (SYSDATETIMEOFFSET()),
        updated_at DATETIMEOFFSET(7) NOT NULL CONSTRAINT DF_karta_user_updated DEFAULT (SYSDATETIMEOFFSET()),
        last_login_at DATETIMEOFFSET(7) NULL,
        CONSTRAINT UQ_karta_user_username UNIQUE (username)
    );
    CREATE INDEX IX_karta_user_active ON dbo.karta_user (is_active, username);
END
GO

IF OBJECT_ID(N'dbo.karta_user_role', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.karta_user_role (
        user_id INT NOT NULL,
        role_code NVARCHAR(64) NOT NULL,
        created_at DATETIMEOFFSET(7) NOT NULL CONSTRAINT DF_karta_user_role_created DEFAULT (SYSDATETIMEOFFSET()),
        CONSTRAINT PK_karta_user_role PRIMARY KEY CLUSTERED (user_id, role_code),
        CONSTRAINT FK_karta_user_role_user FOREIGN KEY (user_id) REFERENCES dbo.karta_user (id) ON DELETE CASCADE,
        CONSTRAINT FK_karta_user_role_role FOREIGN KEY (role_code) REFERENCES dbo.karta_role (code)
    );
END
GO

IF OBJECT_ID(N'dbo.karta_role_permission', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.karta_role_permission (
        role_code NVARCHAR(64) NOT NULL,
        permission_code NVARCHAR(128) NOT NULL,
        created_at DATETIMEOFFSET(7) NOT NULL CONSTRAINT DF_karta_role_permission_created DEFAULT (SYSDATETIMEOFFSET()),
        CONSTRAINT PK_karta_role_permission PRIMARY KEY CLUSTERED (role_code, permission_code),
        CONSTRAINT FK_karta_role_permission_role FOREIGN KEY (role_code) REFERENCES dbo.karta_role (code) ON DELETE CASCADE,
        CONSTRAINT FK_karta_role_permission_permission FOREIGN KEY (permission_code) REFERENCES dbo.karta_permission (code) ON DELETE CASCADE
    );
END
GO

IF OBJECT_ID(N'dbo.karta_user_permission', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.karta_user_permission (
        user_id INT NOT NULL,
        permission_code NVARCHAR(128) NOT NULL,
        created_at DATETIMEOFFSET(7) NOT NULL CONSTRAINT DF_karta_user_permission_created DEFAULT (SYSDATETIMEOFFSET()),
        CONSTRAINT PK_karta_user_permission PRIMARY KEY CLUSTERED (user_id, permission_code),
        CONSTRAINT FK_karta_user_permission_user FOREIGN KEY (user_id) REFERENCES dbo.karta_user (id) ON DELETE CASCADE,
        CONSTRAINT FK_karta_user_permission_permission FOREIGN KEY (permission_code) REFERENCES dbo.karta_permission (code) ON DELETE CASCADE
    );
END
GO

IF OBJECT_ID(N'dbo.karta_user_store', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.karta_user_store (
        user_id INT NOT NULL,
        store_id INT NOT NULL,
        created_at DATETIMEOFFSET(7) NOT NULL CONSTRAINT DF_karta_user_store_created DEFAULT (SYSDATETIMEOFFSET()),
        CONSTRAINT PK_karta_user_store PRIMARY KEY CLUSTERED (user_id, store_id),
        CONSTRAINT FK_karta_user_store_user FOREIGN KEY (user_id) REFERENCES dbo.karta_user (id) ON DELETE CASCADE,
        CONSTRAINT FK_karta_user_store_store FOREIGN KEY (store_id) REFERENCES dbo.karta_store_config (id) ON DELETE CASCADE
    );
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
        hire_date DATE NULL,
        departure_date DATE NULL,
        catering_override BIT NULL,
        work_time_qr_data_url NVARCHAR(MAX) NULL,
        work_time_qr_synced_at DATETIMEOFFSET(7) NULL,
        updated_at DATETIMEOFFSET(7) NOT NULL CONSTRAINT DF_karta_employment_updated DEFAULT (SYSDATETIMEOFFSET()),
        CONSTRAINT FK_karta_employment_employer FOREIGN KEY (employer_id) REFERENCES dbo.karta_employer (id),
        CONSTRAINT FK_karta_employment_employee FOREIGN KEY (employee_id) REFERENCES dbo.karta_employee (id),
        CONSTRAINT FK_karta_employment_parartima FOREIGN KEY (parartima_id) REFERENCES dbo.karta_parartima (id)
    );
    CREATE INDEX IX_karta_employment_employer ON dbo.karta_employment (employer_id);
    CREATE INDEX IX_karta_employment_employee ON dbo.karta_employment (employee_id);
END
GO

IF OBJECT_ID(N'dbo.karta_employment_contract', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.karta_employment_contract (
        id BIGINT NOT NULL IDENTITY(1,1) CONSTRAINT PK_karta_employment_contract PRIMARY KEY CLUSTERED,
        employer_afm NVARCHAR(9) NOT NULL,
        branch_aa NVARCHAR(32) NOT NULL,
        employee_afm NVARCHAR(9) NOT NULL,
        eponymo NVARCHAR(200) NULL,
        onoma NVARCHAR(200) NULL,
        specialty NVARCHAR(200) NULL,
        characterization NVARCHAR(200) NULL,
        step92 NVARCHAR(64) NULL,
        weekly_work_days NVARCHAR(64) NULL,
        prior_service NVARCHAR(64) NULL,
        employment_relation NVARCHAR(200) NULL,
        fixed_term_from NVARCHAR(32) NULL,
        fixed_term_to NVARCHAR(32) NULL,
        regime NVARCHAR(200) NULL,
        weekly_hours NVARCHAR(32) NULL,
        salary NVARCHAR(64) NULL,
        hourly_wage NVARCHAR(64) NULL,
        total_weekly_hours NVARCHAR(32) NULL,
        fulltime_contract_weekly_hours NVARCHAR(32) NULL,
        break_minutes INT NULL,
        break_in_work INT NULL,
        flex_arrival_minutes INT NULL,
        ergani_updated_at NVARCHAR(32) NULL,
        content_hash NVARCHAR(64) NOT NULL,
        is_current BIT NOT NULL CONSTRAINT DF_karta_emp_contract_current DEFAULT (1),
        synced_at DATETIMEOFFSET(7) NOT NULL CONSTRAINT DF_karta_emp_contract_synced DEFAULT (SYSDATETIMEOFFSET()),
        source NVARCHAR(16) NOT NULL CONSTRAINT DF_karta_emp_contract_source DEFAULT (N'portal')
    );
    CREATE INDEX IX_karta_emp_contract_current
        ON dbo.karta_employment_contract (employer_afm, branch_aa, employee_afm, is_current);
    CREATE INDEX IX_karta_emp_contract_history
        ON dbo.karta_employment_contract (employer_afm, branch_aa, employee_afm, synced_at DESC);
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
        protocol_from NVARCHAR(128) NULL,
        protocol_to NVARCHAR(128) NULL,
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
        client_ip NVARCHAR(45) NULL,
        client_device NVARCHAR(2000) NULL,
        submission_channel NVARCHAR(16) NULL,
        submission_ip NVARCHAR(45) NULL,
        executor_instance NVARCHAR(200) NULL,
        created_at DATETIMEOFFSET(7) NOT NULL CONSTRAINT DF_karta_declaration_created DEFAULT (SYSDATETIMEOFFSET())
    );
    CREATE INDEX IX_karta_declaration_code_created ON dbo.karta_declaration (submission_code, created_at DESC);
    CREATE INDEX IX_karta_declaration_submission_ip ON dbo.karta_declaration(submission_ip, created_at DESC)
        INCLUDE (submission_channel, executor_instance, submission_code, success);
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
    CREATE UNIQUE INDEX UQ_karta_card_event_day_type
        ON dbo.karta_card_event (f_afm_ergodoti, f_aa, f_afm, f_reference_date, f_type)
        WHERE f_afm IS NOT NULL
          AND f_reference_date IS NOT NULL
          AND f_type IS NOT NULL
          AND f_afm_ergodoti IS NOT NULL;
END
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
        CONSTRAINT FK_karta_card_listener_store FOREIGN KEY (store_id) REFERENCES dbo.karta_store_config(id) ON DELETE CASCADE,
        CONSTRAINT UQ_karta_card_listener_device_id UNIQUE (device_id)
    );
    CREATE UNIQUE INDEX UX_karta_card_listener_one_active_per_store ON dbo.karta_card_listener_device(store_id)
        WHERE enabled = 1 AND revoked_at IS NULL;
    CREATE INDEX IX_karta_card_listener_store_seen ON dbo.karta_card_listener_device(store_id, enabled, last_seen_at);
END
GO

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
        CONSTRAINT FK_karta_card_listener_job_store FOREIGN KEY (store_id) REFERENCES dbo.karta_store_config(id) ON DELETE CASCADE,
        CONSTRAINT FK_karta_card_listener_job_declaration FOREIGN KEY (declaration_id) REFERENCES dbo.karta_declaration(id),
        CONSTRAINT UQ_karta_card_listener_job_uuid UNIQUE (job_uuid),
        CONSTRAINT UQ_karta_card_listener_job_idempotency UNIQUE (idempotency_key),
        CONSTRAINT CK_karta_card_listener_job_type CHECK (f_type IN (N'0', N'1')),
        CONSTRAINT CK_karta_card_listener_job_status CHECK (status IN (N'queued', N'leased', N'submitting', N'succeeded', N'failed', N'needs_review', N'cancelled_for_fallback', N'fallback_submitting', N'fallback_succeeded', N'fallback_failed'))
    );
    CREATE INDEX IX_karta_card_listener_job_poll ON dbo.karta_card_listener_job(store_id, status, available_at, created_at)
        INCLUDE (job_uuid, fallback_deadline, lease_expires_at);
    CREATE INDEX IX_karta_card_listener_job_status_deadline ON dbo.karta_card_listener_job(status, fallback_deadline);
    CREATE INDEX IX_karta_card_listener_job_employee ON dbo.karta_card_listener_job(store_id, employee_afm, reference_date, f_type);
END
GO

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
        CONSTRAINT FK_karta_card_listener_attempt_job FOREIGN KEY (job_id) REFERENCES dbo.karta_card_listener_job(id) ON DELETE CASCADE,
        CONSTRAINT CK_karta_card_listener_attempt_source CHECK (execution_source IN (N'listener', N'erganios')),
        CONSTRAINT UQ_karta_card_listener_attempt_number UNIQUE (job_id, execution_source, attempt_number)
    );
    CREATE INDEX IX_karta_card_listener_attempt_job ON dbo.karta_card_listener_attempt(job_id, started_at DESC);
END
GO
