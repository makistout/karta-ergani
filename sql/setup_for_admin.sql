/*
  Εκτέλεση ΜΙΑ ΦΟΡΑ στο SSMS ως διαχειριστής (π.χ. sa / Windows admin).
  Server: 95.141.32.37
  Βάση: ergani-karta
  Login εφαρμογής: ergani
*/
USE [master];
GO

IF DB_ID(N'ergani-karta') IS NULL
BEGIN
    CREATE DATABASE [ergani-karta];
    PRINT N'Δημιουργήθηκε η βάση ergani-karta';
END
GO

USE [ergani-karta];
GO

IF NOT EXISTS (SELECT 1 FROM sys.database_principals WHERE name = N'ergani')
BEGIN
    CREATE USER [ergani] FOR LOGIN [ergani];
    PRINT N'Δημιουργήθηκε user ergani';
END
GO

IF IS_ROLEMEMBER(N'db_owner', N'ergani') = 0
BEGIN
    ALTER ROLE [db_owner] ADD MEMBER [ergani];
    PRINT N'Προστέθηκε ergani στο db_owner';
END
GO

/* === schema (ίδιο με sql/schema.sql) === */
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

PRINT N'Ολοκληρώθηκε setup_for_admin.sql';
