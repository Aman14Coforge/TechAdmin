-- TechAdmin Compliance Agent sidecar classification tables
-- This script CREATES new tables only. It does not ALTER existing tables.

BEGIN;
SET LOCAL lock_timeout = '5s';
SET LOCAL statement_timeout = '60s';

CREATE TABLE IF NOT EXISTS techadmin.patch_scan_classification_summaries (
    summary_id UUID PRIMARY KEY,
    scan_id UUID NOT NULL UNIQUE,
    scan_date DATE NOT NULL,
    raw_missing_patch_records INTEGER NOT NULL DEFAULT 0,
    active_non_compliant_devices INTEGER NOT NULL DEFAULT 0,
    persistent_14_devices INTEGER NOT NULL DEFAULT 0,
    stale_reporting_devices INTEGER NOT NULL DEFAULT 0,
    unknown_freshness_devices INTEGER NOT NULL DEFAULT 0,
    resolved_devices INTEGER NOT NULL DEFAULT 0,
    ticket_eligible_devices INTEGER NOT NULL DEFAULT 0,
    freshness_threshold_days INTEGER NOT NULL DEFAULT 7,
    successful_snapshots_available INTEGER NOT NULL DEFAULT 0,
    required_successful_snapshots INTEGER NOT NULL DEFAULT 14,
    calculation_status VARCHAR(30) NOT NULL DEFAULT 'RUNNING',
    calculation_error TEXT,
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at TIMESTAMPTZ,
    duration_seconds DOUBLE PRECISION,
    CONSTRAINT ck_patch_class_summary_status CHECK (
        calculation_status IN ('RUNNING','SUCCEEDED','PARTIAL','FAILED')
    )
);

CREATE TABLE IF NOT EXISTS techadmin.patch_compliance_classifications (
    classification_id UUID PRIMARY KEY,
    scan_id UUID NOT NULL,
    scan_date DATE NOT NULL,
    discovery_id VARCHAR(255) NOT NULL,
    device_name VARCHAR(255) NOT NULL,
    compliance_category VARCHAR(40) NOT NULL,
    freshness_status VARCHAR(30) NOT NULL,
    inclusion_reason TEXT,
    last_scanned_at TIMESTAMPTZ,
    scan_age_days INTEGER,
    missing_patch_count INTEGER NOT NULL DEFAULT 0,
    risk_score DOUBLE PRECISION,
    successful_snapshot_days_14 INTEGER NOT NULL DEFAULT 0,
    required_snapshot_days_14 INTEGER NOT NULL DEFAULT 14,
    persistent_14_days BOOLEAN NOT NULL DEFAULT FALSE,
    assigned_policy VARCHAR(255),
    platform VARCHAR(100),
    os_name VARCHAR(255),
    ip_address VARCHAR(100),
    management_sources JSONB,
    security_critical INTEGER NOT NULL DEFAULT 0,
    security_important INTEGER NOT NULL DEFAULT 0,
    security_moderate INTEGER NOT NULL DEFAULT 0,
    security_low INTEGER NOT NULL DEFAULT 0,
    exploited_missing_patches INTEGER NOT NULL DEFAULT 0,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    resolved_at TIMESTAMPTZ,
    ticket_status VARCHAR(40),
    ticket_reference VARCHAR(255),
    calculated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_patch_classification_device_snapshot UNIQUE (scan_date, discovery_id),
    CONSTRAINT ck_patch_compliance_category CHECK (
        compliance_category IN (
            'ACTIVE_NON_COMPLIANT','PERSISTENT_14_DAYS',
            'STALE_REPORTING','UNKNOWN_FRESHNESS','RESOLVED'
        )
    ),
    CONSTRAINT ck_patch_freshness_status CHECK (
        freshness_status IN ('FRESH','STALE','UNKNOWN','NOT_APPLICABLE')
    )
);

CREATE INDEX IF NOT EXISTS ix_patch_class_summary_date
ON techadmin.patch_scan_classification_summaries (scan_date DESC);
CREATE INDEX IF NOT EXISTS ix_patch_class_date_category
ON techadmin.patch_compliance_classifications (scan_date DESC, compliance_category);
CREATE INDEX IF NOT EXISTS ix_patch_class_device_date
ON techadmin.patch_compliance_classifications (discovery_id, scan_date DESC);
CREATE INDEX IF NOT EXISTS ix_patch_class_persistent
ON techadmin.patch_compliance_classifications (scan_date DESC, persistent_14_days)
WHERE persistent_14_days IS TRUE;
CREATE INDEX IF NOT EXISTS ix_patch_class_scan_id
ON techadmin.patch_compliance_classifications (scan_id);

COMMIT;
