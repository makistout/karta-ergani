/* Περιβάλλον Ergani API ανά κατάστημα: production | trial */
IF COL_LENGTH(N'dbo.karta_store_config', N'ergani_env') IS NULL
BEGIN
    ALTER TABLE dbo.karta_store_config
    ADD ergani_env NVARCHAR(16) NOT NULL
        CONSTRAINT DF_karta_store_ergani_env DEFAULT (N'production');
END
GO

UPDATE dbo.karta_store_config
SET ergani_env = N'production'
WHERE ergani_env IS NULL OR LTRIM(RTRIM(ergani_env)) = N'';
GO
