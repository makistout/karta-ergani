/* Telegram inbound messages and Gemini-parsed dry-run commands. */
SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
GO

IF OBJECT_ID(N'dbo.karta_telegram_inbound_message', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.karta_telegram_inbound_message (
        id BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT PK_karta_telegram_inbound PRIMARY KEY,
        telegram_update_id BIGINT NOT NULL,
        telegram_message_id BIGINT NULL,
        reply_to_message_id BIGINT NULL,
        chat_id NVARCHAR(64) NOT NULL,
        recipient_id INT NULL,
        store_id INT NULL,
        message_text NVARCHAR(MAX) NULL,
        raw_payload_json NVARCHAR(MAX) NULL,
        processing_status NVARCHAR(32) NOT NULL CONSTRAINT DF_karta_telegram_inbound_status DEFAULT N'received',
        error_message NVARCHAR(2000) NULL,
        received_at DATETIMEOFFSET(7) NOT NULL CONSTRAINT DF_karta_telegram_inbound_received DEFAULT SYSDATETIMEOFFSET(),
        processed_at DATETIMEOFFSET(7) NULL,
        CONSTRAINT UQ_karta_telegram_inbound_update UNIQUE (telegram_update_id),
        CONSTRAINT FK_karta_telegram_inbound_recipient FOREIGN KEY (recipient_id) REFERENCES dbo.karta_store_notify_recipient(id),
        CONSTRAINT FK_karta_telegram_inbound_store FOREIGN KEY (store_id) REFERENCES dbo.karta_store_config(id)
    );
    CREATE INDEX IX_karta_telegram_inbound_chat ON dbo.karta_telegram_inbound_message(chat_id, received_at DESC);
END
GO

IF OBJECT_ID(N'dbo.karta_telegram_outbound_message', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.karta_telegram_outbound_message (
        id BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT PK_karta_telegram_outbound PRIMARY KEY,
        telegram_message_id BIGINT NOT NULL,
        chat_id NVARCHAR(64) NOT NULL,
        recipient_id INT NULL,
        store_id INT NULL,
        employee_afm NVARCHAR(16) NULL,
        notification_type NVARCHAR(64) NULL,
        notification_reference_id NVARCHAR(128) NULL,
        message_text NVARCHAR(MAX) NULL,
        context_json NVARCHAR(MAX) NULL,
        sent_at DATETIMEOFFSET(7) NOT NULL CONSTRAINT DF_karta_telegram_outbound_sent DEFAULT SYSDATETIMEOFFSET(),
        CONSTRAINT UQ_karta_telegram_outbound_message UNIQUE (chat_id, telegram_message_id),
        CONSTRAINT FK_karta_telegram_outbound_recipient FOREIGN KEY (recipient_id) REFERENCES dbo.karta_store_notify_recipient(id),
        CONSTRAINT FK_karta_telegram_outbound_store FOREIGN KEY (store_id) REFERENCES dbo.karta_store_config(id)
    );
    CREATE INDEX IX_karta_telegram_outbound_reply ON dbo.karta_telegram_outbound_message(chat_id, telegram_message_id);
END
GO

IF OBJECT_ID(N'dbo.karta_assistant_task', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.karta_assistant_task (
        id BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT PK_karta_assistant_task PRIMARY KEY,
        inbound_message_id BIGINT NOT NULL,
        recipient_id INT NULL,
        store_id INT NULL,
        intent NVARCHAR(64) NOT NULL,
        task_status NVARCHAR(32) NOT NULL,
        employee_afm NVARCHAR(16) NULL,
        work_date DATE NULL,
        payload_json NVARCHAR(MAX) NOT NULL,
        llm_response_json NVARCHAR(MAX) NULL,
        confidence DECIMAL(5,4) NULL,
        validation_json NVARCHAR(MAX) NULL,
        proposed_action_text NVARCHAR(2000) NULL,
        execution_enabled BIT NOT NULL CONSTRAINT DF_karta_assistant_task_execution DEFAULT (0),
        confirmed_at DATETIMEOFFSET(7) NULL,
        executed_at DATETIMEOFFSET(7) NULL,
        protocol NVARCHAR(128) NULL,
        error_message NVARCHAR(2000) NULL,
        created_at DATETIMEOFFSET(7) NOT NULL CONSTRAINT DF_karta_assistant_task_created DEFAULT SYSDATETIMEOFFSET(),
        updated_at DATETIMEOFFSET(7) NOT NULL CONSTRAINT DF_karta_assistant_task_updated DEFAULT SYSDATETIMEOFFSET(),
        CONSTRAINT UQ_karta_assistant_task_inbound UNIQUE (inbound_message_id),
        CONSTRAINT FK_karta_assistant_task_inbound FOREIGN KEY (inbound_message_id) REFERENCES dbo.karta_telegram_inbound_message(id),
        CONSTRAINT FK_karta_assistant_task_recipient FOREIGN KEY (recipient_id) REFERENCES dbo.karta_store_notify_recipient(id),
        CONSTRAINT FK_karta_assistant_task_store FOREIGN KEY (store_id) REFERENCES dbo.karta_store_config(id)
    );
    CREATE INDEX IX_karta_assistant_task_status ON dbo.karta_assistant_task(task_status, created_at DESC);
    CREATE INDEX IX_karta_assistant_task_store ON dbo.karta_assistant_task(store_id, created_at DESC);
END
GO

IF OBJECT_ID(N'dbo.karta_assistant_task_event', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.karta_assistant_task_event (
        id BIGINT IDENTITY(1,1) NOT NULL CONSTRAINT PK_karta_assistant_task_event PRIMARY KEY,
        task_id BIGINT NOT NULL,
        event_type NVARCHAR(64) NOT NULL,
        event_json NVARCHAR(MAX) NULL,
        created_at DATETIMEOFFSET(7) NOT NULL CONSTRAINT DF_karta_assistant_task_event_created DEFAULT SYSDATETIMEOFFSET(),
        CONSTRAINT FK_karta_assistant_task_event_task FOREIGN KEY (task_id) REFERENCES dbo.karta_assistant_task(id)
    );
    CREATE INDEX IX_karta_assistant_task_event_task ON dbo.karta_assistant_task_event(task_id, id);
END
GO
