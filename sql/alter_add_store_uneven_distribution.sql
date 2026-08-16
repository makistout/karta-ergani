/*
  Επιθυμία χρήσης ανισομερούς κατανομής — ανά κατάστημα.
  Default ΟΧΙ για όλα τα υπάρχοντα και νέα καταστήματα.
*/

IF COL_LENGTH(N'dbo.karta_store_config', N'uneven_distribution_enabled') IS NULL
BEGIN
    ALTER TABLE dbo.karta_store_config
        ADD uneven_distribution_enabled BIT NOT NULL
            CONSTRAINT DF_karta_store_uneven_distribution_enabled DEFAULT (0);
    PRINT N'OK: uneven_distribution_enabled';
END
GO
