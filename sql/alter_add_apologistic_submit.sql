IF OBJECT_ID(N'dbo.karta_apologistic_submit', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.karta_apologistic_submit (
        id BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT PK_karta_apologistic_submit PRIMARY KEY,
        day_id BIGINT NOT NULL,
        submission_code NVARCHAR(32) NOT NULL,
        declaration_id BIGINT NULL,
        proposed_at_submit NVARCHAR(64) NULL,
        segment_reference_date DATE NULL,
        protocol NVARCHAR(64) NULL,
        ergani_submission_id NVARCHAR(32) NULL,
        submit_date_text NVARCHAR(64) NULL,
        success BIT NOT NULL CONSTRAINT DF_karta_apologistic_submit_success DEFAULT (0),
        submitted_by NVARCHAR(128) NULL,
        submitted_at DATETIMEOFFSET(7) NOT NULL CONSTRAINT DF_karta_apologistic_submit_at DEFAULT SYSDATETIMEOFFSET(),
        CONSTRAINT FK_karta_apologistic_submit_day FOREIGN KEY (day_id) REFERENCES dbo.karta_apologistic_day(id) ON DELETE CASCADE,
        CONSTRAINT FK_karta_apologistic_submit_declaration FOREIGN KEY (declaration_id) REFERENCES dbo.karta_declaration(id)
    );
    CREATE INDEX IX_karta_apologistic_submit_day_code ON dbo.karta_apologistic_submit(day_id, submission_code, segment_reference_date, submitted_at DESC);
END
GO
