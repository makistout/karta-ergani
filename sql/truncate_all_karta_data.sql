/*
  Διαγραφή ΟΛΩΝ των δεδομένων karta_* (όχι τα tables).
  Βάση: ergani-karta — τρέξτε ως login με δικαιώματα DELETE.
*/
SET NOCOUNT ON;

BEGIN TRANSACTION;

IF OBJECT_ID(N'dbo.karta_card_event', N'U') IS NOT NULL
    DELETE FROM dbo.karta_card_event;

IF OBJECT_ID(N'dbo.karta_declaration', N'U') IS NOT NULL
    DELETE FROM dbo.karta_declaration;

IF OBJECT_ID(N'dbo.karta_schedule', N'U') IS NOT NULL
    DELETE FROM dbo.karta_schedule;

IF OBJECT_ID(N'dbo.karta_work_log', N'U') IS NOT NULL
    DELETE FROM dbo.karta_work_log;

IF OBJECT_ID(N'dbo.karta_employment', N'U') IS NOT NULL
    DELETE FROM dbo.karta_employment;

IF OBJECT_ID(N'dbo.karta_parartima', N'U') IS NOT NULL
    DELETE FROM dbo.karta_parartima;

IF OBJECT_ID(N'dbo.karta_employee', N'U') IS NOT NULL
    DELETE FROM dbo.karta_employee;

IF OBJECT_ID(N'dbo.karta_employer', N'U') IS NOT NULL
    DELETE FROM dbo.karta_employer;

IF OBJECT_ID(N'dbo.karta_store_config', N'U') IS NOT NULL
    DELETE FROM dbo.karta_store_config;

COMMIT TRANSACTION;

SELECT N'karta_store_config' AS tbl, COUNT(*) AS cnt FROM dbo.karta_store_config
UNION ALL SELECT N'karta_employer', COUNT(*) FROM dbo.karta_employer
UNION ALL SELECT N'karta_employee', COUNT(*) FROM dbo.karta_employee
UNION ALL SELECT N'karta_schedule', COUNT(*) FROM dbo.karta_schedule
UNION ALL SELECT N'karta_work_log', COUNT(*) FROM dbo.karta_work_log
UNION ALL SELECT N'karta_declaration', COUNT(*) FROM dbo.karta_declaration
UNION ALL SELECT N'karta_card_event', COUNT(*) FROM dbo.karta_card_event;
