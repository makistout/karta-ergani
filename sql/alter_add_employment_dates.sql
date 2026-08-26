SET NOCOUNT ON;

IF COL_LENGTH(N'dbo.karta_employment', N'hire_date') IS NULL
    ALTER TABLE dbo.karta_employment ADD hire_date DATE NULL;

IF COL_LENGTH(N'dbo.karta_employment', N'departure_date') IS NULL
    ALTER TABLE dbo.karta_employment ADD departure_date DATE NULL;
