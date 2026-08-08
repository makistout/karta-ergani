-- Στοιχεία σύμβασης προσωπικού (append-only snapshots από Ergani Μητρώα)
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
    PRINT N'OK: karta_employment_contract';
END
GO
