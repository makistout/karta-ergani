IF COL_LENGTH(N'dbo.karta_user', N'email_verified_at') IS NULL
BEGIN
    ALTER TABLE dbo.karta_user
        ADD email_verified_at DATETIMEOFFSET(7) NULL;
    PRINT N'OK: email_verified_at';
END
GO

IF COL_LENGTH(N'dbo.karta_user', N'email_verification_token_hash') IS NULL
BEGIN
    ALTER TABLE dbo.karta_user
        ADD email_verification_token_hash NVARCHAR(128) NULL;
    PRINT N'OK: email_verification_token_hash';
END
GO

IF COL_LENGTH(N'dbo.karta_user', N'email_verification_sent_at') IS NULL
BEGIN
    ALTER TABLE dbo.karta_user
        ADD email_verification_sent_at DATETIMEOFFSET(7) NULL;
    PRINT N'OK: email_verification_sent_at';
END
GO

IF COL_LENGTH(N'dbo.karta_user', N'email_verification_expires_at') IS NULL
BEGIN
    ALTER TABLE dbo.karta_user
        ADD email_verification_expires_at DATETIMEOFFSET(7) NULL;
    PRINT N'OK: email_verification_expires_at';
END
GO

IF NOT EXISTS (
    SELECT 1
    FROM sys.indexes
    WHERE name = N'IX_karta_user_email_verification_token'
      AND object_id = OBJECT_ID(N'dbo.karta_user')
)
BEGIN
    CREATE INDEX IX_karta_user_email_verification_token
        ON dbo.karta_user (email_verification_token_hash)
        WHERE email_verification_token_hash IS NOT NULL;
    PRINT N'OK: IX_karta_user_email_verification_token';
END
GO
