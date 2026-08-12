IF OBJECT_ID(N'dbo.karta_apologistic_rest_obligation', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.karta_apologistic_rest_obligation (
        id BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT PK_karta_apologistic_rest_obligation PRIMARY KEY,
        store_id INT NOT NULL,
        employee_afm NVARCHAR(9) NOT NULL,
        source_run_id BIGINT NULL,
        source_work_date DATE NOT NULL,
        source_actual_minutes INT NOT NULL,
        source_punch_days INT NOT NULL,
        target_week_from DATE NOT NULL,
        target_week_to DATE NOT NULL,
        status NVARCHAR(24) NOT NULL CONSTRAINT DF_karta_apologistic_rest_status DEFAULT (N'pending'),
        resolved_work_date DATE NULL,
        resolved_by NVARCHAR(128) NULL,
        resolution_note NVARCHAR(1000) NULL,
        resolved_at DATETIMEOFFSET(7) NULL,
        created_at DATETIMEOFFSET(7) NOT NULL CONSTRAINT DF_karta_apologistic_rest_created DEFAULT SYSDATETIMEOFFSET(),
        updated_at DATETIMEOFFSET(7) NOT NULL CONSTRAINT DF_karta_apologistic_rest_updated DEFAULT SYSDATETIMEOFFSET(),
        CONSTRAINT FK_karta_apologistic_rest_store FOREIGN KEY (store_id) REFERENCES dbo.karta_store_config(id) ON DELETE CASCADE,
        CONSTRAINT FK_karta_apologistic_rest_run FOREIGN KEY (source_run_id) REFERENCES dbo.karta_apologistic_run(id),
        CONSTRAINT UQ_karta_apologistic_rest_source UNIQUE (store_id, employee_afm, source_work_date),
        CONSTRAINT CK_karta_apologistic_rest_status CHECK (status IN (N'pending', N'satisfied', N'cancelled'))
    );
    CREATE INDEX IX_karta_apologistic_rest_target ON dbo.karta_apologistic_rest_obligation(store_id, target_week_from, status, employee_afm);
END
GO
