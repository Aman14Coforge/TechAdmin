-- Run while connected to the TechAdmin database with DB_SCHEMA as the active
-- schema (the same schema configured in the application's .env file).
-- This migration is idempotent and adds password-safe chat-history fields to
-- operation_requests. Existing audit records remain valid and can still be
-- viewed as individual requests.

DO $$
DECLARE
    target_schema TEXT := current_schema();
BEGIN
    EXECUTE format(
        'ALTER TABLE %I.operation_requests ADD COLUMN IF NOT EXISTS conversation_id VARCHAR(64)',
        target_schema
    );
    EXECUTE format(
        'ALTER TABLE %I.operation_requests ADD COLUMN IF NOT EXISTS response_summary TEXT',
        target_schema
    );
    EXECUTE format(
        'ALTER TABLE %I.operation_requests ADD COLUMN IF NOT EXISTS response_payload JSON',
        target_schema
    );
    EXECUTE format(
        'ALTER TABLE %I.operation_requests ADD COLUMN IF NOT EXISTS response_saved_at TIMESTAMPTZ',
        target_schema
    );
    EXECUTE format(
        'CREATE INDEX IF NOT EXISTS ix_operation_requests_conversation_id '
        'ON %I.operation_requests (conversation_id) WHERE conversation_id IS NOT NULL',
        target_schema
    );
END $$;
