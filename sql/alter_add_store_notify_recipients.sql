/*
  Migration: λήπτες ειδοποιήσεων Telegram ανά κατάστημα
*/
SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
GO

IF OBJECT_ID(N'dbo.karta_store_notify_recipient', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.karta_store_notify_recipient (
        id INT NOT NULL IDENTITY(1,1) CONSTRAINT PK_karta_store_notify_recipient PRIMARY KEY CLUSTERED,
        store_id INT NOT NULL,
        name NVARCHAR(128) NOT NULL,
        mobile NVARCHAR(32) NOT NULL,
        telegram_chat_id NVARCHAR(64) NULL,
        email NVARCHAR(254) NULL,
        active BIT NOT NULL CONSTRAINT DF_karta_notify_active DEFAULT (1),
        email_active BIT NOT NULL CONSTRAINT DF_karta_notify_email_active DEFAULT (1),
        notify_repeat_policy NVARCHAR(32) NOT NULL
            CONSTRAINT DF_karta_notify_repeat_policy DEFAULT (N'once_snooze'),
        created_at DATETIMEOFFSET(7) NOT NULL CONSTRAINT DF_karta_notify_created DEFAULT (SYSDATETIMEOFFSET()),
        CONSTRAINT FK_karta_notify_store FOREIGN KEY (store_id)
            REFERENCES dbo.karta_store_config (id) ON DELETE CASCADE
    );
    CREATE INDEX IX_karta_notify_store ON dbo.karta_store_notify_recipient (store_id);
    CREATE INDEX IX_karta_notify_mobile ON dbo.karta_store_notify_recipient (mobile);
    PRINT N'OK: karta_store_notify_recipient';
END
GO

IF OBJECT_ID(N'dbo.karta_store_notify_recipient', N'U') IS NOT NULL
   AND COL_LENGTH(N'dbo.karta_store_notify_recipient', N'notify_repeat_policy') IS NULL
BEGIN
    ALTER TABLE dbo.karta_store_notify_recipient
        ADD notify_repeat_policy NVARCHAR(32) NOT NULL
            CONSTRAINT DF_karta_notify_repeat_policy DEFAULT (N'once_snooze');
    PRINT N'OK: karta_store_notify_recipient.notify_repeat_policy';
END
GO

IF OBJECT_ID(N'dbo.karta_store_notify_recipient', N'U') IS NOT NULL
   AND COL_LENGTH(N'dbo.karta_store_notify_recipient', N'email') IS NULL
BEGIN
    ALTER TABLE dbo.karta_store_notify_recipient
        ADD email NVARCHAR(254) NULL;
    PRINT N'OK: karta_store_notify_recipient.email';
END
GO

IF OBJECT_ID(N'dbo.karta_store_notify_recipient', N'U') IS NOT NULL
   AND COL_LENGTH(N'dbo.karta_store_notify_recipient', N'email_active') IS NULL
BEGIN
    ALTER TABLE dbo.karta_store_notify_recipient
        ADD email_active BIT NOT NULL
            CONSTRAINT DF_karta_notify_email_active DEFAULT (1);
    PRINT N'OK: karta_store_notify_recipient.email_active';
END
GO
