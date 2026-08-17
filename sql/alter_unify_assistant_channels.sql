/* Add channel identity to the existing canonical assistant message stream. */

IF COL_LENGTH(N'dbo.karta_telegram_inbound_message', N'channel') IS NULL
BEGIN
    ALTER TABLE dbo.karta_telegram_inbound_message ADD channel NVARCHAR(16) NOT NULL
        CONSTRAINT DF_karta_assistant_inbound_channel DEFAULT (N'telegram') WITH VALUES;
END
GO
IF COL_LENGTH(N'dbo.karta_telegram_inbound_message', N'office_user') IS NULL
    ALTER TABLE dbo.karta_telegram_inbound_message ADD office_user NVARCHAR(128) NULL;
GO
IF COL_LENGTH(N'dbo.karta_telegram_outbound_message', N'channel') IS NULL
BEGIN
    ALTER TABLE dbo.karta_telegram_outbound_message ADD channel NVARCHAR(16) NOT NULL
        CONSTRAINT DF_karta_assistant_outbound_channel DEFAULT (N'telegram') WITH VALUES;
END
GO
IF COL_LENGTH(N'dbo.karta_telegram_outbound_message', N'office_user') IS NULL
    ALTER TABLE dbo.karta_telegram_outbound_message ADD office_user NVARCHAR(128) NULL;
GO
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name=N'IX_karta_assistant_inbound_store_channel' AND object_id=OBJECT_ID(N'dbo.karta_telegram_inbound_message'))
    CREATE INDEX IX_karta_assistant_inbound_store_channel
        ON dbo.karta_telegram_inbound_message(store_id, channel, received_at DESC);
GO
