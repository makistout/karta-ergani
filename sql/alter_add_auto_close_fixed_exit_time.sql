/*
  Προαιρετική σταθερή ώρα κλεισίματος ανοιχτών καρτών.
  NULL/κενό = έξοδος βάσει διάρκειας ωραρίου (υπάρχουσα λογική).
  Π.χ. 23:00 = όλες οι ανοιχτές έξοδοι τυχαία μέσα στο [23:00, 23:30).
*/

IF COL_LENGTH(N'dbo.karta_store_config', N'auto_close_fixed_exit_time') IS NULL
BEGIN
    ALTER TABLE dbo.karta_store_config
        ADD auto_close_fixed_exit_time NVARCHAR(5) NULL;
    PRINT N'OK: auto_close_fixed_exit_time';
END
GO
