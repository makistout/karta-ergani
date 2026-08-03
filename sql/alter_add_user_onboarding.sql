-- Onboarding: υποχρεωτική αλλαγή κωδικού + αποδοχή όρων (με IP/χρόνο)

IF COL_LENGTH(N'dbo.karta_user', N'must_change_password') IS NULL
BEGIN
    ALTER TABLE dbo.karta_user
        ADD must_change_password BIT NOT NULL
            CONSTRAINT DF_karta_user_must_change_password DEFAULT (0);
    PRINT N'OK: must_change_password';
END
GO

IF COL_LENGTH(N'dbo.karta_user', N'terms_accepted_at') IS NULL
BEGIN
    ALTER TABLE dbo.karta_user
        ADD terms_accepted_at DATETIMEOFFSET(7) NULL;
    PRINT N'OK: terms_accepted_at';
END
GO

IF COL_LENGTH(N'dbo.karta_user', N'terms_accepted_ip') IS NULL
BEGIN
    ALTER TABLE dbo.karta_user
        ADD terms_accepted_ip NVARCHAR(64) NULL;
    PRINT N'OK: terms_accepted_ip';
END
GO

IF COL_LENGTH(N'dbo.karta_user', N'terms_version') IS NULL
BEGIN
    ALTER TABLE dbo.karta_user
        ADD terms_version NVARCHAR(32) NULL;
    PRINT N'OK: terms_version';
END
GO

-- Υπάρχοντες χρήστες: δεν μπλοκάρονται (grandfather)
IF COL_LENGTH(N'dbo.karta_user', N'terms_accepted_at') IS NOT NULL
BEGIN
    UPDATE dbo.karta_user
    SET must_change_password = 0,
        terms_accepted_at = COALESCE(terms_accepted_at, SYSDATETIMEOFFSET()),
        terms_accepted_ip = COALESCE(terms_accepted_ip, N'migration'),
        terms_version = COALESCE(terms_version, N'pre-onboarding')
    WHERE terms_accepted_at IS NULL
       OR terms_version IS NULL;
    PRINT N'OK: grandfathered existing users';
END
GO
