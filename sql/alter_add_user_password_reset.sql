-- Self-service password reset tokens

IF COL_LENGTH(N'dbo.karta_user', N'password_reset_token_hash') IS NULL
BEGIN
    ALTER TABLE dbo.karta_user
        ADD password_reset_token_hash NVARCHAR(128) NULL;
    PRINT N'OK: password_reset_token_hash';
END
GO

IF COL_LENGTH(N'dbo.karta_user', N'password_reset_sent_at') IS NULL
BEGIN
    ALTER TABLE dbo.karta_user
        ADD password_reset_sent_at DATETIMEOFFSET(7) NULL;
    PRINT N'OK: password_reset_sent_at';
END
GO

IF COL_LENGTH(N'dbo.karta_user', N'password_reset_expires_at') IS NULL
BEGIN
    ALTER TABLE dbo.karta_user
        ADD password_reset_expires_at DATETIMEOFFSET(7) NULL;
    PRINT N'OK: password_reset_expires_at';
END
GO

IF NOT EXISTS (
    SELECT 1
    FROM sys.indexes
    WHERE name = N'IX_karta_user_password_reset_token'
      AND object_id = OBJECT_ID(N'dbo.karta_user')
)
BEGIN
    CREATE INDEX IX_karta_user_password_reset_token
        ON dbo.karta_user (password_reset_token_hash)
        WHERE password_reset_token_hash IS NOT NULL;
    PRINT N'OK: IX_karta_user_password_reset_token';
END
GO
