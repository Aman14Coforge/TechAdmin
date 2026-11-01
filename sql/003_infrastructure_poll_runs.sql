CREATE TABLE IF NOT EXISTS infrastructure_poll_runs (
    id BIGSERIAL PRIMARY KEY,
    trigger_type VARCHAR(32) NOT NULL,
    status VARCHAR(32) NOT NULL,
    source_sync_run_id TEXT,
    alerts_found INTEGER NOT NULL DEFAULT 0,
    tickets_attempted INTEGER NOT NULL DEFAULT 0,
    tickets_created INTEGER NOT NULL DEFAULT 0,
    sites_skipped INTEGER NOT NULL DEFAULT 0,
    sites_recovered INTEGER NOT NULL DEFAULT 0,
    emails_sent INTEGER NOT NULL DEFAULT 0,
    email_sites INTEGER NOT NULL DEFAULT 0,
    error_count INTEGER NOT NULL DEFAULT 0,
    error_summary TEXT,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ,
    duration_seconds NUMERIC
);

CREATE INDEX IF NOT EXISTS ix_infrastructure_poll_runs_started_at
ON infrastructure_poll_runs (started_at DESC);
