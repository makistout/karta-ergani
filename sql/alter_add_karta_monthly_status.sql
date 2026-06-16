/*
  Migration: μηνιαία κατάσταση απασχόλησης (EX_BASE_04)
*/
SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
GO

IF OBJECT_ID(N'dbo.karta_monthly_status', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.karta_monthly_status (
        id BIGINT NOT NULL IDENTITY(1,1) CONSTRAINT PK_karta_monthly_status PRIMARY KEY CLUSTERED,
        employer_afm NVARCHAR(9) NOT NULL,
        branch_aa NVARCHAR(32) NOT NULL,
        ergodoti_id NVARCHAR(32) NULL,
        report_year INT NOT NULL,
        report_month INT NOT NULL,
        employee_afm NVARCHAR(9) NOT NULL,
        days_work INT NULL,
        days_telework INT NULL,
        days_repo INT NULL,
        days_no_work INT NULL,
        days_normal_leave INT NULL,
        overtime_minutes INT NULL,
        overtime_days INT NULL,
        days_work_card INT NULL,
        days_leave_insurance INT NULL,
        days_sick_insurance INT NULL,
        synced_at DATETIMEOFFSET(7) NOT NULL CONSTRAINT DF_karta_monthly_status_synced DEFAULT (SYSDATETIMEOFFSET()),
        CONSTRAINT UQ_karta_monthly_status UNIQUE (employer_afm, branch_aa, report_year, report_month, employee_afm)
    );
    CREATE INDEX IX_karta_monthly_status_lookup
        ON dbo.karta_monthly_status (employer_afm, branch_aa, report_year, report_month);
    PRINT N'OK: karta_monthly_status';
END
GO
