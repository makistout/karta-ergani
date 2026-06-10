/*
  Αποτροπή διπλής καταχώρησης κάρτας (ίδιος εργαζόμενος / ημέρα / τύπος / εργοδότης / παράρτημα).
*/
SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
GO

IF NOT EXISTS (
    SELECT 1 FROM sys.indexes
    WHERE name = N'UQ_karta_card_event_day_type'
      AND object_id = OBJECT_ID(N'dbo.karta_card_event')
)
BEGIN
    CREATE UNIQUE INDEX UQ_karta_card_event_day_type
        ON dbo.karta_card_event (f_afm_ergodoti, f_aa, f_afm, f_reference_date, f_type)
        WHERE f_afm IS NOT NULL
          AND f_reference_date IS NOT NULL
          AND f_type IS NOT NULL
          AND f_afm_ergodoti IS NOT NULL;
    PRINT N'OK: UQ_karta_card_event_day_type';
END
GO
