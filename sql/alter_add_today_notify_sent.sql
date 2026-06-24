/*
  Καταγραφή αυτόματων ειδοποιήσεων τύπου 2 — μία φορά ανά περίπτωση/ημέρα.
*/
SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
GO

IF OBJECT_ID(N'dbo.karta_today_notify_sent', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.karta_today_notify_sent (
        id INT IDENTITY(1,1) NOT NULL PRIMARY KEY,
        store_id INT NOT NULL,
        employee_afm NVARCHAR(9) NOT NULL,
        work_date_ergani NVARCHAR(32) NOT NULL,
        notify_kind NVARCHAR(32) NOT NULL,
        sent_via NVARCHAR(32) NOT NULL DEFAULT N'auto_post_sync',
        sent_at DATETIMEOFFSET(7) NOT NULL DEFAULT SYSDATETIMEOFFSET(),
        CONSTRAINT FK_today_notify_sent_store
            FOREIGN KEY (store_id) REFERENCES dbo.karta_store_config(id),
        CONSTRAINT UQ_today_notify_sent_case
            UNIQUE (store_id, employee_afm, work_date_ergani, notify_kind)
    );
    CREATE INDEX IX_today_notify_sent_store_date
        ON dbo.karta_today_notify_sent (store_id, work_date_ergani);
    PRINT N'OK: karta_today_notify_sent';
END
GO
