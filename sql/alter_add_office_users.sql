SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
GO

IF OBJECT_ID(N'dbo.karta_role', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.karta_role (
        code NVARCHAR(64) NOT NULL CONSTRAINT PK_karta_role PRIMARY KEY CLUSTERED,
        name NVARCHAR(128) NOT NULL,
        description NVARCHAR(500) NULL,
        created_at DATETIMEOFFSET(7) NOT NULL CONSTRAINT DF_karta_role_created DEFAULT (SYSDATETIMEOFFSET()),
        updated_at DATETIMEOFFSET(7) NOT NULL CONSTRAINT DF_karta_role_updated DEFAULT (SYSDATETIMEOFFSET())
    );
END
GO

IF OBJECT_ID(N'dbo.karta_permission', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.karta_permission (
        code NVARCHAR(128) NOT NULL CONSTRAINT PK_karta_permission PRIMARY KEY CLUSTERED,
        name NVARCHAR(200) NOT NULL,
        description NVARCHAR(500) NULL,
        created_at DATETIMEOFFSET(7) NOT NULL CONSTRAINT DF_karta_permission_created DEFAULT (SYSDATETIMEOFFSET()),
        updated_at DATETIMEOFFSET(7) NOT NULL CONSTRAINT DF_karta_permission_updated DEFAULT (SYSDATETIMEOFFSET())
    );
END
GO

IF OBJECT_ID(N'dbo.karta_user', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.karta_user (
        id INT NOT NULL IDENTITY(1,1) CONSTRAINT PK_karta_user PRIMARY KEY CLUSTERED,
        username NVARCHAR(128) NOT NULL,
        email NVARCHAR(255) NULL,
        password_hash NVARCHAR(512) NOT NULL,
        full_name NVARCHAR(200) NULL,
        is_active BIT NOT NULL CONSTRAINT DF_karta_user_active DEFAULT (1),
        is_super_admin BIT NOT NULL CONSTRAINT DF_karta_user_super DEFAULT (0),
        created_at DATETIMEOFFSET(7) NOT NULL CONSTRAINT DF_karta_user_created DEFAULT (SYSDATETIMEOFFSET()),
        updated_at DATETIMEOFFSET(7) NOT NULL CONSTRAINT DF_karta_user_updated DEFAULT (SYSDATETIMEOFFSET()),
        last_login_at DATETIMEOFFSET(7) NULL,
        CONSTRAINT UQ_karta_user_username UNIQUE (username)
    );
    CREATE INDEX IX_karta_user_active ON dbo.karta_user (is_active, username);
END
GO

IF OBJECT_ID(N'dbo.karta_user_role', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.karta_user_role (
        user_id INT NOT NULL,
        role_code NVARCHAR(64) NOT NULL,
        created_at DATETIMEOFFSET(7) NOT NULL CONSTRAINT DF_karta_user_role_created DEFAULT (SYSDATETIMEOFFSET()),
        CONSTRAINT PK_karta_user_role PRIMARY KEY CLUSTERED (user_id, role_code),
        CONSTRAINT FK_karta_user_role_user FOREIGN KEY (user_id) REFERENCES dbo.karta_user (id) ON DELETE CASCADE,
        CONSTRAINT FK_karta_user_role_role FOREIGN KEY (role_code) REFERENCES dbo.karta_role (code)
    );
END
GO

IF OBJECT_ID(N'dbo.karta_role_permission', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.karta_role_permission (
        role_code NVARCHAR(64) NOT NULL,
        permission_code NVARCHAR(128) NOT NULL,
        created_at DATETIMEOFFSET(7) NOT NULL CONSTRAINT DF_karta_role_permission_created DEFAULT (SYSDATETIMEOFFSET()),
        CONSTRAINT PK_karta_role_permission PRIMARY KEY CLUSTERED (role_code, permission_code),
        CONSTRAINT FK_karta_role_permission_role FOREIGN KEY (role_code) REFERENCES dbo.karta_role (code) ON DELETE CASCADE,
        CONSTRAINT FK_karta_role_permission_permission FOREIGN KEY (permission_code) REFERENCES dbo.karta_permission (code) ON DELETE CASCADE
    );
END
GO

IF OBJECT_ID(N'dbo.karta_user_permission', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.karta_user_permission (
        user_id INT NOT NULL,
        permission_code NVARCHAR(128) NOT NULL,
        created_at DATETIMEOFFSET(7) NOT NULL CONSTRAINT DF_karta_user_permission_created DEFAULT (SYSDATETIMEOFFSET()),
        CONSTRAINT PK_karta_user_permission PRIMARY KEY CLUSTERED (user_id, permission_code),
        CONSTRAINT FK_karta_user_permission_user FOREIGN KEY (user_id) REFERENCES dbo.karta_user (id) ON DELETE CASCADE,
        CONSTRAINT FK_karta_user_permission_permission FOREIGN KEY (permission_code) REFERENCES dbo.karta_permission (code) ON DELETE CASCADE
    );
END
GO

IF OBJECT_ID(N'dbo.karta_user_store', N'U') IS NULL
BEGIN
    CREATE TABLE dbo.karta_user_store (
        user_id INT NOT NULL,
        store_id INT NOT NULL,
        created_at DATETIMEOFFSET(7) NOT NULL CONSTRAINT DF_karta_user_store_created DEFAULT (SYSDATETIMEOFFSET()),
        CONSTRAINT PK_karta_user_store PRIMARY KEY CLUSTERED (user_id, store_id),
        CONSTRAINT FK_karta_user_store_user FOREIGN KEY (user_id) REFERENCES dbo.karta_user (id) ON DELETE CASCADE,
        CONSTRAINT FK_karta_user_store_store FOREIGN KEY (store_id) REFERENCES dbo.karta_store_config (id) ON DELETE CASCADE
    );
END
GO
