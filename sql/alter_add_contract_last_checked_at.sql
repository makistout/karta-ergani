-- NULL on existing snapshots: historical checks cannot be reconstructed.
IF COL_LENGTH(N'dbo.karta_employment_contract', N'last_checked_at') IS NULL
BEGIN
    ALTER TABLE dbo.karta_employment_contract
        ADD last_checked_at DATETIMEOFFSET(7) NULL;
END
