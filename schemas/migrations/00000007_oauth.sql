-- OAuth Provider Migration for AYON Server
-- Add OAuth client support

-- OAuth clients table
CREATE TABLE IF NOT EXISTS oauth_clients (
    client_id VARCHAR(64) PRIMARY KEY,
    client_secret TEXT,
    client_name VARCHAR(255) NOT NULL,
    redirect_uris TEXT[] DEFAULT '{}',
    grant_types TEXT[] DEFAULT '{authorization_code,refresh_token}',
    response_types TEXT[] DEFAULT '{code}',
    scope VARCHAR(255) DEFAULT 'read',
    client_type VARCHAR(20) DEFAULT 'confidential',
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Create indexes for OAuth clients
CREATE INDEX IF NOT EXISTS idx_oauth_clients_client_id ON oauth_clients(client_id);
CREATE INDEX IF NOT EXISTS idx_oauth_clients_active ON oauth_clients(is_active);
CREATE INDEX IF NOT EXISTS idx_oauth_clients_name ON oauth_clients(client_name);

-- Add updated_at trigger for OAuth clients
CREATE OR REPLACE FUNCTION update_oauth_clients_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW."updated_at" := NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS oauth_clients_updated_at ON oauth_clients;
CREATE TRIGGER oauth_clients_updated_at
    BEFORE UPDATE ON oauth_clients
    FOR EACH ROW
    EXECUTE FUNCTION update_oauth_clients_updated_at();
