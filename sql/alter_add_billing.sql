-- Τιμολόγηση πελατών. Νέοι πίνακες μόνο· δεν αλλάζει karta_store_config.
IF OBJECT_ID(N'dbo.karta_billing_customer', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.karta_billing_customer (
        id INT NOT NULL IDENTITY(1,1) CONSTRAINT PK_karta_billing_customer PRIMARY KEY CLUSTERED,
        eponimia NVARCHAR(200) NOT NULL,
        epaggelma NVARCHAR(200) NULL,
        address NVARCHAR(400) NULL,
        afm NVARCHAR(16) NOT NULL,
        doy NVARCHAR(120) NULL,
        email NVARCHAR(200) NULL,
        phone NVARCHAR(40) NULL,
        notes NVARCHAR(1000) NULL,
        is_active BIT NOT NULL CONSTRAINT DF_karta_billing_customer_active DEFAULT (1),
        created_at DATETIMEOFFSET(7) NOT NULL CONSTRAINT DF_karta_billing_customer_created DEFAULT (SYSDATETIMEOFFSET()),
        updated_at DATETIMEOFFSET(7) NOT NULL CONSTRAINT DF_karta_billing_customer_updated DEFAULT (SYSDATETIMEOFFSET())
    );
    CREATE UNIQUE INDEX UX_karta_billing_customer_afm ON dbo.karta_billing_customer (afm);
    PRINT N'OK: karta_billing_customer';
END
GO

IF OBJECT_ID(N'dbo.karta_billing_customer_store', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.karta_billing_customer_store (
        customer_id INT NOT NULL,
        store_id INT NOT NULL,
        created_at DATETIMEOFFSET(7) NOT NULL CONSTRAINT DF_karta_billing_cstore_created DEFAULT (SYSDATETIMEOFFSET()),
        CONSTRAINT PK_karta_billing_customer_store PRIMARY KEY CLUSTERED (customer_id, store_id),
        CONSTRAINT FK_karta_billing_cstore_customer FOREIGN KEY (customer_id)
            REFERENCES dbo.karta_billing_customer(id),
        CONSTRAINT FK_karta_billing_cstore_store FOREIGN KEY (store_id)
            REFERENCES dbo.karta_store_config(id)
    );
    CREATE UNIQUE INDEX UX_karta_billing_cstore_store ON dbo.karta_billing_customer_store (store_id);
    PRINT N'OK: karta_billing_customer_store';
END
GO

IF OBJECT_ID(N'dbo.karta_billing_plan', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.karta_billing_plan (
        id INT NOT NULL IDENTITY(1,1) CONSTRAINT PK_karta_billing_plan PRIMARY KEY CLUSTERED,
        code NVARCHAR(64) NOT NULL,
        name NVARCHAR(200) NOT NULL,
        months INT NOT NULL,
        includes_erganios BIT NOT NULL CONSTRAINT DF_karta_billing_plan_erganios DEFAULT (1),
        includes_apologistic BIT NOT NULL CONSTRAINT DF_karta_billing_plan_apo DEFAULT (0),
        includes_ai_agent BIT NOT NULL CONSTRAINT DF_karta_billing_plan_ai DEFAULT (0),
        amount_net DECIMAL(12,2) NOT NULL CONSTRAINT DF_karta_billing_plan_net DEFAULT (0),
        vat_rate DECIMAL(5,2) NOT NULL CONSTRAINT DF_karta_billing_plan_vat DEFAULT (24),
        is_active BIT NOT NULL CONSTRAINT DF_karta_billing_plan_active DEFAULT (1),
        CONSTRAINT UX_karta_billing_plan_code UNIQUE (code),
        CONSTRAINT CK_karta_billing_plan_months CHECK (months IN (6, 12))
    );
    PRINT N'OK: karta_billing_plan';
END
GO

IF OBJECT_ID(N'dbo.karta_billing_subscription', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.karta_billing_subscription (
        id INT NOT NULL IDENTITY(1,1) CONSTRAINT PK_karta_billing_subscription PRIMARY KEY CLUSTERED,
        customer_id INT NOT NULL,
        plan_id INT NOT NULL,
        starts_on DATE NOT NULL,
        ends_on DATE NOT NULL,
        status NVARCHAR(16) NOT NULL CONSTRAINT DF_karta_billing_sub_status DEFAULT (N'active'),
        amount_net DECIMAL(12,2) NOT NULL,
        vat_rate DECIMAL(5,2) NOT NULL,
        notes NVARCHAR(400) NULL,
        created_at DATETIMEOFFSET(7) NOT NULL CONSTRAINT DF_karta_billing_sub_created DEFAULT (SYSDATETIMEOFFSET()),
        CONSTRAINT FK_karta_billing_sub_customer FOREIGN KEY (customer_id)
            REFERENCES dbo.karta_billing_customer(id),
        CONSTRAINT FK_karta_billing_sub_plan FOREIGN KEY (plan_id)
            REFERENCES dbo.karta_billing_plan(id),
        CONSTRAINT CK_karta_billing_sub_status CHECK (status IN (N'active', N'expired', N'cancelled'))
    );
    CREATE INDEX IX_karta_billing_sub_customer ON dbo.karta_billing_subscription (customer_id, status);
    PRINT N'OK: karta_billing_subscription';
END
GO

IF OBJECT_ID(N'dbo.karta_billing_document', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.karta_billing_document (
        id INT NOT NULL IDENTITY(1,1) CONSTRAINT PK_karta_billing_document PRIMARY KEY CLUSTERED,
        customer_id INT NOT NULL,
        doc_type NVARCHAR(16) NOT NULL,
        series NVARCHAR(16) NOT NULL CONSTRAINT DF_karta_billing_doc_series DEFAULT (N'A'),
        number INT NULL,
        issued_on DATE NULL,
        status NVARCHAR(16) NOT NULL CONSTRAINT DF_karta_billing_doc_status DEFAULT (N'draft'),
        total_net DECIMAL(12,2) NOT NULL CONSTRAINT DF_karta_billing_doc_net DEFAULT (0),
        total_vat DECIMAL(12,2) NOT NULL CONSTRAINT DF_karta_billing_doc_vat DEFAULT (0),
        total_gross DECIMAL(12,2) NOT NULL CONSTRAINT DF_karta_billing_doc_gross DEFAULT (0),
        notes NVARCHAR(1000) NULL,
        created_at DATETIMEOFFSET(7) NOT NULL CONSTRAINT DF_karta_billing_doc_created DEFAULT (SYSDATETIMEOFFSET()),
        CONSTRAINT FK_karta_billing_doc_customer FOREIGN KEY (customer_id)
            REFERENCES dbo.karta_billing_customer(id),
        CONSTRAINT CK_karta_billing_doc_type CHECK (doc_type IN (N'APY', N'TPY', N'CREDIT')),
        CONSTRAINT CK_karta_billing_doc_status CHECK (status IN (N'draft', N'issued', N'cancelled'))
    );
    CREATE UNIQUE INDEX UX_karta_billing_doc_number
        ON dbo.karta_billing_document (doc_type, series, number)
        WHERE number IS NOT NULL AND status = N'issued';
    PRINT N'OK: karta_billing_document';
END
GO

IF OBJECT_ID(N'dbo.karta_billing_entry', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.karta_billing_entry (
        id INT NOT NULL IDENTITY(1,1) CONSTRAINT PK_karta_billing_entry PRIMARY KEY CLUSTERED,
        customer_id INT NOT NULL,
        kind NVARCHAR(16) NOT NULL,
        description NVARCHAR(400) NOT NULL,
        amount_net DECIMAL(12,2) NOT NULL,
        vat_rate DECIMAL(5,2) NOT NULL CONSTRAINT DF_karta_billing_entry_vat DEFAULT (24),
        entry_date DATE NOT NULL,
        subscription_id INT NULL,
        document_id INT NULL,
        created_at DATETIMEOFFSET(7) NOT NULL CONSTRAINT DF_karta_billing_entry_created DEFAULT (SYSDATETIMEOFFSET()),
        CONSTRAINT FK_karta_billing_entry_customer FOREIGN KEY (customer_id)
            REFERENCES dbo.karta_billing_customer(id),
        CONSTRAINT FK_karta_billing_entry_sub FOREIGN KEY (subscription_id)
            REFERENCES dbo.karta_billing_subscription(id),
        CONSTRAINT FK_karta_billing_entry_doc FOREIGN KEY (document_id)
            REFERENCES dbo.karta_billing_document(id),
        CONSTRAINT CK_karta_billing_entry_kind CHECK (kind IN (N'charge', N'credit'))
    );
    CREATE INDEX IX_karta_billing_entry_customer ON dbo.karta_billing_entry (customer_id, entry_date);
    PRINT N'OK: karta_billing_entry';
END
GO

IF NOT EXISTS (SELECT 1 FROM dbo.karta_billing_plan WHERE code = N'erganios_apologistic_12m')
    INSERT INTO dbo.karta_billing_plan (code, name, months, includes_erganios, includes_apologistic, includes_ai_agent)
    VALUES (N'erganios_apologistic_12m', N'ErganiOS + Απολογιστικό 12 μήνες', 12, 1, 1, 0);
IF NOT EXISTS (SELECT 1 FROM dbo.karta_billing_plan WHERE code = N'erganios_apologistic_6m')
    INSERT INTO dbo.karta_billing_plan (code, name, months, includes_erganios, includes_apologistic, includes_ai_agent)
    VALUES (N'erganios_apologistic_6m', N'ErganiOS + Απολογιστικό 6 μήνες', 6, 1, 1, 0);
IF NOT EXISTS (SELECT 1 FROM dbo.karta_billing_plan WHERE code = N'erganios_ai_12m')
    INSERT INTO dbo.karta_billing_plan (code, name, months, includes_erganios, includes_apologistic, includes_ai_agent)
    VALUES (N'erganios_ai_12m', N'ErganiOS + AI Agent 12 μήνες', 12, 1, 0, 1);
IF NOT EXISTS (SELECT 1 FROM dbo.karta_billing_plan WHERE code = N'erganios_ai_6m')
    INSERT INTO dbo.karta_billing_plan (code, name, months, includes_erganios, includes_apologistic, includes_ai_agent)
    VALUES (N'erganios_ai_6m', N'ErganiOS + AI Agent 6 μήνες', 6, 1, 0, 1);
PRINT N'OK: billing plans';
GO
