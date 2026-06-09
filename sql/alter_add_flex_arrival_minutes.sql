/*
  Migration: ευέλικτη προσέλευση (λεπτά) από EX_BASE_05 / EueliktoWrario
*/
SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
GO

IF COL_LENGTH(N'dbo.karta_employee', N'flex_arrival_minutes') IS NULL
BEGIN
    ALTER TABLE dbo.karta_employee
        ADD flex_arrival_minutes INT NULL;
    PRINT N'OK: karta_employee.flex_arrival_minutes';
END
GO
