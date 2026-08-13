/*
  Μεταφορά ΡΕΠΟ λόγω εργασίας Κυριακής (6η ημέρα πενθημέρου) — ανά κατάστημα.
  Default ΟΧΙ για όλα· ενεργοποιείται ρητά από τις ρυθμίσεις ενεργειών.
*/

IF COL_LENGTH(N'dbo.karta_store_config', N'sunday_rest_transfer_enabled') IS NULL
BEGIN
    ALTER TABLE dbo.karta_store_config
        ADD sunday_rest_transfer_enabled BIT NOT NULL
            CONSTRAINT DF_karta_store_sunday_rest_transfer_enabled DEFAULT (0);
    PRINT N'OK: sunday_rest_transfer_enabled';
END
GO

UPDATE dbo.karta_store_config
SET sunday_rest_transfer_enabled = CASE WHEN id IN (13, 14) THEN 1 ELSE 0 END,
    updated_at = SYSDATETIMEOFFSET();
GO
