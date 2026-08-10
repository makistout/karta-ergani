SET XACT_ABORT ON;
BEGIN TRANSACTION;
IF COL_LENGTH(N'dbo.karta_declaration', N'submission_channel') IS NULL ALTER TABLE dbo.karta_declaration ADD submission_channel NVARCHAR(16) NULL;
IF COL_LENGTH(N'dbo.karta_declaration', N'submission_ip') IS NULL ALTER TABLE dbo.karta_declaration ADD submission_ip NVARCHAR(45) NULL;
IF COL_LENGTH(N'dbo.karta_declaration', N'executor_instance') IS NULL ALTER TABLE dbo.karta_declaration ADD executor_instance NVARCHAR(200) NULL;
IF COL_LENGTH(N'dbo.karta_card_listener_device', N'last_seen_ip') IS NULL ALTER TABLE dbo.karta_card_listener_device ADD last_seen_ip NVARCHAR(45) NULL;
IF COL_LENGTH(N'dbo.karta_card_listener_job', N'submission_ip') IS NULL ALTER TABLE dbo.karta_card_listener_job ADD submission_ip NVARCHAR(45) NULL;
IF COL_LENGTH(N'dbo.karta_card_listener_job', N'executor_instance') IS NULL ALTER TABLE dbo.karta_card_listener_job ADD executor_instance NVARCHAR(200) NULL;
IF COL_LENGTH(N'dbo.karta_card_listener_attempt', N'submission_ip') IS NULL ALTER TABLE dbo.karta_card_listener_attempt ADD submission_ip NVARCHAR(45) NULL;
IF COL_LENGTH(N'dbo.karta_card_listener_attempt', N'executor_instance') IS NULL ALTER TABLE dbo.karta_card_listener_attempt ADD executor_instance NVARCHAR(200) NULL;
IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE object_id = OBJECT_ID(N'dbo.karta_declaration') AND name = N'IX_karta_declaration_submission_ip')
    EXEC(N'CREATE INDEX IX_karta_declaration_submission_ip ON dbo.karta_declaration(submission_ip, created_at DESC) INCLUDE (submission_channel, executor_instance, submission_code, success)');
COMMIT TRANSACTION;
GO
