/*
  Ειδοποίηση τύπου 2 — τρέχουσα ημέρα (token + snooze).
*/
SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
GO

IF OBJECT_ID(N'dbo.karta_telegram_today_alert_token', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.karta_telegram_today_alert_token (
        id INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        token_hash CHAR(64) NOT NULL UNIQUE,
        recipient_id INT NOT NULL,
        store_id INT NOT NULL,
        employee_afm NVARCHAR(9) NOT NULL,
        eponymo NVARCHAR(200) NULL,
        onoma NVARCHAR(200) NULL,
        work_date_ergani NVARCHAR(32) NOT NULL,
        reference_date_iso CHAR(10) NOT NULL,
        notify_kind NVARCHAR(32) NOT NULL,
        hour_from NVARCHAR(8) NULL,
        hour_to NVARCHAR(8) NULL,
        schedule_hour_from NVARCHAR(8) NULL,
        pin_attempts INT NOT NULL DEFAULT 0,
        pin_verified_at DATETIMEOFFSET(7) NULL,
        action_taken NVARCHAR(32) NULL,
        created_at DATETIMEOFFSET(7) NOT NULL DEFAULT SYSDATETIMEOFFSET(),
        expires_at DATETIMEOFFSET(7) NOT NULL,
        used_at DATETIMEOFFSET(7) NULL,
        CONSTRAINT FK_today_alert_recipient
            FOREIGN KEY (recipient_id) REFERENCES dbo.karta_store_notify_recipient(id),
        CONSTRAINT FK_today_alert_store
            FOREIGN KEY (store_id) REFERENCES dbo.karta_store_config(id)
    );
    CREATE INDEX IX_today_alert_store_emp_date
        ON dbo.karta_telegram_today_alert_token (store_id, employee_afm, work_date_ergani);
    PRINT N'OK: karta_telegram_today_alert_token';
END
GO

IF OBJECT_ID(N'dbo.karta_today_notify_snooze', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.karta_today_notify_snooze (
        id INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        store_id INT NOT NULL,
        recipient_id INT NULL,
        employee_afm NVARCHAR(9) NOT NULL,
        work_date_ergani NVARCHAR(32) NOT NULL,
        notify_kind NVARCHAR(32) NOT NULL,
        created_at DATETIMEOFFSET(7) NOT NULL DEFAULT SYSDATETIMEOFFSET(),
        acted_by_name NVARCHAR(200) NULL,
        acted_by_mobile NVARCHAR(32) NULL,
        acted_via NVARCHAR(32) NULL,
        office_user NVARCHAR(128) NULL,
        client_ip NVARCHAR(45) NULL,
        client_device NVARCHAR(2000) NULL,
        CONSTRAINT FK_today_snooze_store
            FOREIGN KEY (store_id) REFERENCES dbo.karta_store_config(id),
        CONSTRAINT UQ_today_snooze_case
            UNIQUE (store_id, employee_afm, work_date_ergani, notify_kind)
    );
    PRINT N'OK: karta_today_notify_snooze';
END
GO
