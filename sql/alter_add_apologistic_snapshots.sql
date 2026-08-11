IF OBJECT_ID(N'dbo.karta_apologistic_run', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.karta_apologistic_run (
        id BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT PK_karta_apologistic_run PRIMARY KEY,
        store_id INT NOT NULL,
        employer_afm NVARCHAR(9) NOT NULL,
        branch_aa NVARCHAR(32) NOT NULL,
        week_from DATE NOT NULL,
        week_to DATE NOT NULL,
        status NVARCHAR(24) NOT NULL CONSTRAINT DF_karta_apologistic_run_status DEFAULT (N'draft'),
        calculation_version NVARCHAR(40) NOT NULL,
        generated_report_json NVARCHAR(MAX) NULL,
        effective_report_json NVARCHAR(MAX) NULL,
        error_summary NVARCHAR(2000) NULL,
        started_at DATETIMEOFFSET(7) NULL,
        completed_at DATETIMEOFFSET(7) NULL,
        created_at DATETIMEOFFSET(7) NOT NULL CONSTRAINT DF_karta_apologistic_run_created DEFAULT SYSDATETIMEOFFSET(),
        updated_at DATETIMEOFFSET(7) NOT NULL CONSTRAINT DF_karta_apologistic_run_updated DEFAULT SYSDATETIMEOFFSET(),
        CONSTRAINT FK_karta_apologistic_run_store FOREIGN KEY (store_id) REFERENCES dbo.karta_store_config(id) ON DELETE CASCADE,
        CONSTRAINT UQ_karta_apologistic_run_store_week UNIQUE (store_id, week_from),
        CONSTRAINT CK_karta_apologistic_run_status CHECK (status IN (N'running', N'draft', N'failed', N'approved', N'locked'))
    );
    CREATE INDEX IX_karta_apologistic_run_week ON dbo.karta_apologistic_run(week_from, status, store_id);
END
GO

IF OBJECT_ID(N'dbo.karta_apologistic_day', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.karta_apologistic_day (
        id BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT PK_karta_apologistic_day PRIMARY KEY,
        run_id BIGINT NOT NULL,
        store_id INT NOT NULL,
        employee_afm NVARCHAR(9) NOT NULL,
        work_date DATE NOT NULL,
        generated_json NVARCHAR(MAX) NOT NULL,
        override_json NVARCHAR(MAX) NULL,
        effective_json NVARCHAR(MAX) NOT NULL,
        review_status NVARCHAR(24) NOT NULL CONSTRAINT DF_karta_apologistic_day_review DEFAULT (N'draft'),
        override_reason NVARCHAR(1000) NULL,
        updated_by NVARCHAR(128) NULL,
        override_updated_at DATETIMEOFFSET(7) NULL,
        generated_at DATETIMEOFFSET(7) NOT NULL CONSTRAINT DF_karta_apologistic_day_generated DEFAULT SYSDATETIMEOFFSET(),
        updated_at DATETIMEOFFSET(7) NOT NULL CONSTRAINT DF_karta_apologistic_day_updated DEFAULT SYSDATETIMEOFFSET(),
        CONSTRAINT FK_karta_apologistic_day_run FOREIGN KEY (run_id) REFERENCES dbo.karta_apologistic_run(id) ON DELETE CASCADE,
        CONSTRAINT FK_karta_apologistic_day_store FOREIGN KEY (store_id) REFERENCES dbo.karta_store_config(id),
        CONSTRAINT UQ_karta_apologistic_day_key UNIQUE (run_id, employee_afm, work_date),
        CONSTRAINT CK_karta_apologistic_day_review CHECK (review_status IN (N'draft', N'reviewed', N'approved', N'locked'))
    );
    CREATE INDEX IX_karta_apologistic_day_store_date ON dbo.karta_apologistic_day(store_id, work_date, employee_afm);
END
GO
