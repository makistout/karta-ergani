IF OBJECT_ID(N'dbo.karta_apologistic_change', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.karta_apologistic_change (
        id BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT PK_karta_apologistic_change PRIMARY KEY,
        day_id BIGINT NOT NULL,
        field_name NVARCHAR(64) NOT NULL,
        old_value NVARCHAR(2000) NULL,
        new_value NVARCHAR(2000) NULL,
        changed_by NVARCHAR(128) NULL,
        changed_at DATETIMEOFFSET(7) NOT NULL CONSTRAINT DF_karta_apologistic_change_at DEFAULT SYSDATETIMEOFFSET(),
        CONSTRAINT FK_karta_apologistic_change_day FOREIGN KEY (day_id) REFERENCES dbo.karta_apologistic_day(id) ON DELETE CASCADE
    );
    CREATE INDEX IX_karta_apologistic_change_day_field ON dbo.karta_apologistic_change(day_id, field_name, changed_at DESC);
END
GO
