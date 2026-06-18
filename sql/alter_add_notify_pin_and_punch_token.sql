/*
  PIN λήπτη + tokens αυτόματου χτυπήματος κάρτας από Telegram
*/
SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
GO

IF COL_LENGTH(N'dbo.karta_store_notify_recipient', N'notify_pin_hash') IS NULL
BEGIN
    ALTER TABLE dbo.karta_store_notify_recipient
        ADD notify_pin_hash NVARCHAR(128) NULL;
    PRINT N'OK: notify_pin_hash';
END
GO

IF OBJECT_ID(N'dbo.karta_telegram_punch_token', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.karta_telegram_punch_token (
        id BIGINT NOT NULL IDENTITY(1,1)
            CONSTRAINT PK_karta_telegram_punch_token PRIMARY KEY CLUSTERED,
        token_hash NVARCHAR(64) NOT NULL,
        recipient_id INT NOT NULL,
        store_id INT NOT NULL,
        employee_afm NVARCHAR(9) NOT NULL,
        eponymo NVARCHAR(200) NULL,
        onoma NVARCHAR(200) NULL,
        work_date_ergani NVARCHAR(32) NOT NULL,
        reference_date_iso NVARCHAR(10) NOT NULL,
        card_event NVARCHAR(16) NOT NULL,
        retro_time NVARCHAR(8) NOT NULL,
        created_at DATETIMEOFFSET(7) NOT NULL
            CONSTRAINT DF_karta_tg_punch_created DEFAULT (SYSDATETIMEOFFSET()),
        expires_at DATETIMEOFFSET(7) NOT NULL,
        used_at DATETIMEOFFSET(7) NULL,
        pin_attempts INT NOT NULL CONSTRAINT DF_karta_tg_punch_attempts DEFAULT (0),
        CONSTRAINT FK_karta_tg_punch_recipient FOREIGN KEY (recipient_id)
            REFERENCES dbo.karta_store_notify_recipient (id) ON DELETE CASCADE,
        CONSTRAINT FK_karta_tg_punch_store FOREIGN KEY (store_id)
            REFERENCES dbo.karta_store_config (id)
    );
    CREATE UNIQUE INDEX UQ_karta_tg_punch_token_hash
        ON dbo.karta_telegram_punch_token (token_hash);
    CREATE INDEX IX_karta_tg_punch_expires ON dbo.karta_telegram_punch_token (expires_at);
    PRINT N'OK: karta_telegram_punch_token';
END
GO
