/*
  Μετρητής αποστολών ειδοποίησης ανά λήπτη/περίπτωση (πολιτική twice_snooze).
*/
SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
GO

IF OBJECT_ID(N'dbo.karta_today_notify_recipient_send', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.karta_today_notify_recipient_send (
        id INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        store_id INT NOT NULL,
        recipient_id INT NOT NULL,
        employee_afm NVARCHAR(9) NOT NULL,
        work_date_ergani NVARCHAR(32) NOT NULL,
        notify_kind NVARCHAR(32) NOT NULL,
        send_count INT NOT NULL CONSTRAINT DF_today_notify_recipient_send_count DEFAULT (0),
        last_sent_at DATETIMEOFFSET(7) NOT NULL CONSTRAINT DF_today_notify_recipient_send_at DEFAULT (SYSDATETIMEOFFSET()),
        CONSTRAINT FK_today_notify_recipient_send_store
            FOREIGN KEY (store_id) REFERENCES dbo.karta_store_config(id),
        CONSTRAINT FK_today_notify_recipient_send_recipient
            FOREIGN KEY (recipient_id) REFERENCES dbo.karta_store_notify_recipient(id),
        CONSTRAINT UQ_today_notify_recipient_send_case
            UNIQUE (store_id, recipient_id, employee_afm, work_date_ergani, notify_kind)
    );
    CREATE INDEX IX_today_notify_recipient_send_lookup
        ON dbo.karta_today_notify_recipient_send (store_id, work_date_ergani, employee_afm);
    PRINT N'OK: karta_today_notify_recipient_send';
END
GO
