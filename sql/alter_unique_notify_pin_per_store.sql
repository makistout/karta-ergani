/*
  Μοναδικός PIN λήπτη ανά κατάστημα.
  Αν υπάρχουν ήδη διπλότυπα PIN, τα εμφανίζει και δεν δημιουργεί το index.
*/

IF OBJECT_ID(N'dbo.karta_store_notify_recipient', N'U') IS NULL
BEGIN
    RAISERROR(N'Λείπει ο πίνακας dbo.karta_store_notify_recipient.', 16, 1);
END
GO

IF NOT EXISTS (
    SELECT 1
    FROM sys.indexes
    WHERE name = N'UQ_karta_notify_store_pin'
      AND object_id = OBJECT_ID(N'dbo.karta_store_notify_recipient')
)
BEGIN
    IF EXISTS (
        SELECT 1
        FROM dbo.karta_store_notify_recipient
        WHERE notify_pin IS NOT NULL
          AND LTRIM(RTRIM(notify_pin)) <> N''
        GROUP BY store_id, LTRIM(RTRIM(notify_pin))
        HAVING COUNT(*) > 1
    )
    BEGIN
        SELECT
            store_id,
            LTRIM(RTRIM(notify_pin)) AS duplicate_notify_pin,
            COUNT(*) AS duplicate_count
        FROM dbo.karta_store_notify_recipient
        WHERE notify_pin IS NOT NULL
          AND LTRIM(RTRIM(notify_pin)) <> N''
        GROUP BY store_id, LTRIM(RTRIM(notify_pin))
        HAVING COUNT(*) > 1;
        RAISERROR(N'Υπάρχουν διπλότυπα PIN στο ίδιο κατάστημα. Διορθώστε τα πριν δημιουργηθεί το unique index.', 16, 1);
    END
    ELSE
    BEGIN
        CREATE UNIQUE INDEX UQ_karta_notify_store_pin
            ON dbo.karta_store_notify_recipient (store_id, notify_pin)
            WHERE notify_pin IS NOT NULL
              AND notify_pin <> N'';
        PRINT N'OK: UQ_karta_notify_store_pin';
    END
END
GO
