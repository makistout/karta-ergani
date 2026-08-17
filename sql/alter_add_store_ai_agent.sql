/* Per-store AI Agent subscription flag. Existing and new stores default to disabled. */

IF COL_LENGTH(N'dbo.karta_store_config', N'ai_agent_enabled') IS NULL
BEGIN
    ALTER TABLE dbo.karta_store_config
        ADD ai_agent_enabled BIT NOT NULL
            CONSTRAINT DF_karta_store_ai_agent_enabled DEFAULT (0) WITH VALUES;
    PRINT N'OK: ai_agent_enabled';
END
GO
