-- ITOM sync_run_id values can exceed PostgreSQL BIGINT (signed 64-bit).
-- Preserve them as opaque text identifiers.
ALTER TABLE infrastructure_site_incidents
ALTER COLUMN sync_run_id TYPE TEXT
USING sync_run_id::text;
