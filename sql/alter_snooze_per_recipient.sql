/*
  Snooze ανά λήπτη — όχι global ανά υπόθεση εργαζομένου.
  Παλιό UQ: (store_id, employee_afm, work_date_ergani, notify_kind)
  Νέο UQ: (store_id, recipient_id, employee_afm, work_date_ergani, notify_kind)
*/
SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
GO

IF OBJECT_ID(N'dbo.karta_today_notify_snooze', N'U') IS NULL
BEGIN
    RAISERROR(N'Λείπει ο πίνακας dbo.karta_today_notify_snooze.', 16, 1);
END
GO

IF EXISTS (
    SELECT 1 FROM sys.key_constraints
    WHERE parent_object_id = OBJECT_ID(N'dbo.karta_today_notify_snooze')
      AND name = N'UQ_today_snooze_case'
)
BEGIN
    ALTER TABLE dbo.karta_today_notify_snooze DROP CONSTRAINT UQ_today_snooze_case;
    PRINT N'OK: dropped UQ_today_snooze_case';
END
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.key_constraints
    WHERE parent_object_id = OBJECT_ID(N'dbo.karta_today_notify_snooze')
      AND name = N'UQ_today_snooze_recipient_case'
)
BEGIN
    ALTER TABLE dbo.karta_today_notify_snooze
        ADD CONSTRAINT UQ_today_snooze_recipient_case
            UNIQUE (store_id, recipient_id, employee_afm, work_date_ergani, notify_kind);
    PRINT N'OK: UQ_today_snooze_recipient_case';
END
GO
