SET NOCOUNT ON;

IF COL_LENGTH(N'dbo.karta_employment', N'catering_override') IS NULL
    ALTER TABLE dbo.karta_employment ADD catering_override BIT NULL;
