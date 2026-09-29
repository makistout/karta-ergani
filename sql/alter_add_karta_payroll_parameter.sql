IF OBJECT_ID(N'dbo.karta_payroll_parameter', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.karta_payroll_parameter (
        id INT NOT NULL IDENTITY(1,1) CONSTRAINT PK_karta_payroll_parameter PRIMARY KEY CLUSTERED,
        store_id INT NOT NULL CONSTRAINT DF_karta_payroll_parameter_store DEFAULT (0),
        code NVARCHAR(64) NOT NULL,
        value NVARCHAR(64) NOT NULL,
        value_kind NVARCHAR(16) NOT NULL CONSTRAINT DF_karta_payroll_parameter_kind DEFAULT (N'percent'),
        valid_from DATE NOT NULL CONSTRAINT DF_karta_payroll_parameter_from DEFAULT ('20000101'),
        valid_to DATE NULL,
        label NVARCHAR(200) NOT NULL,
        group_code NVARCHAR(32) NOT NULL CONSTRAINT DF_karta_payroll_parameter_group DEFAULT (N'custom'),
        sort_order INT NOT NULL CONSTRAINT DF_karta_payroll_parameter_sort DEFAULT (900),
        legal_ref NVARCHAR(200) NULL,
        note NVARCHAR(400) NULL,
        updated_at DATETIME2 NOT NULL CONSTRAINT DF_karta_payroll_parameter_upd DEFAULT (SYSUTCDATETIME()),
        updated_by NVARCHAR(100) NULL
    );
    CREATE UNIQUE INDEX UX_karta_payroll_parameter
        ON dbo.karta_payroll_parameter (store_id, code, valid_from);
    CREATE INDEX IX_karta_payroll_parameter_lookup
        ON dbo.karta_payroll_parameter (store_id, code, valid_from, valid_to);
    PRINT N'OK: dbo.karta_payroll_parameter';
END
GO
