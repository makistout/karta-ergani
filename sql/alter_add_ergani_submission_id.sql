/* Υπάρχουσα εγκατάσταση: προσθήκη id από απάντηση Ergani [{"id","protocol","submitDate"}] */
IF COL_LENGTH('dbo.karta_declaration', 'ergani_submission_id') IS NULL
BEGIN
    ALTER TABLE dbo.karta_declaration
        ADD ergani_submission_id NVARCHAR(32) NULL;
END
GO
