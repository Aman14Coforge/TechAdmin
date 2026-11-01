"""Persistence for Infrastructure Agent incidents and poll-run history.

This repository stores:
- the latest state of every monitored infrastructure site;
- iEngage ticket and consolidated-email results for each site;
- one audit row for every manual, startup, and scheduled poll.

Schema creation and additive migrations are idempotent. Existing Identity Agent
and Compliance Agent tables are not modified.
"""
from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import text

from App.db.connection import SessionLocal
from App.services.infrastructure.models import InfrastructureSiteAlert


INCIDENT_DDL = """
CREATE TABLE IF NOT EXISTS infrastructure_site_incidents (
    id BIGSERIAL PRIMARY KEY,
    location_name VARCHAR(255) NOT NULL UNIQUE,
    current_status VARCHAR(32) NOT NULL,
    priority VARCHAR(8),
    sync_run_id TEXT,
    site_score NUMERIC,
    site_reason TEXT,
    affected_count INTEGER NOT NULL DEFAULT 0,
    ticket_status VARCHAR(32),
    ticket_id VARCHAR(128),
    ticket_message TEXT,
    ticket_description TEXT,
    solarwinds_prompt TEXT,
    email_status VARCHAR(32),
    email_message TEXT,
    detail_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    first_detected_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_detected_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_ticketed_at TIMESTAMPTZ,
    last_emailed_at TIMESTAMPTZ,
    recovered_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
)
"""

POLL_RUN_DDL = """
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
)
"""

POLL_RUN_INDEX_DDL = """
CREATE INDEX IF NOT EXISTS ix_infrastructure_poll_runs_started_at
ON infrastructure_poll_runs (started_at DESC)
"""

INCIDENT_STATUS_INDEX_DDL = """
CREATE INDEX IF NOT EXISTS ix_infrastructure_site_incidents_status
ON infrastructure_site_incidents (current_status, priority)
"""

INCIDENT_UPDATED_INDEX_DDL = """
CREATE INDEX IF NOT EXISTS ix_infrastructure_site_incidents_updated_at
ON infrastructure_site_incidents (updated_at DESC)
"""

# CREATE TABLE IF NOT EXISTS does not update an existing table. Every new
# poll-history column therefore has an additive migration here.
POLL_RUN_MIGRATIONS = (
    """
    ALTER TABLE infrastructure_poll_runs
    ADD COLUMN IF NOT EXISTS trigger_type VARCHAR(32) NOT NULL DEFAULT 'scheduled'
    """,
    """
    ALTER TABLE infrastructure_poll_runs
    ADD COLUMN IF NOT EXISTS status VARCHAR(32) NOT NULL DEFAULT 'completed'
    """,
    """
    ALTER TABLE infrastructure_poll_runs
    ADD COLUMN IF NOT EXISTS source_sync_run_id TEXT
    """,
    """
    ALTER TABLE infrastructure_poll_runs
    ADD COLUMN IF NOT EXISTS alerts_found INTEGER NOT NULL DEFAULT 0
    """,
    """
    ALTER TABLE infrastructure_poll_runs
    ADD COLUMN IF NOT EXISTS tickets_attempted INTEGER NOT NULL DEFAULT 0
    """,
    """
    ALTER TABLE infrastructure_poll_runs
    ADD COLUMN IF NOT EXISTS tickets_created INTEGER NOT NULL DEFAULT 0
    """,
    """
    ALTER TABLE infrastructure_poll_runs
    ADD COLUMN IF NOT EXISTS sites_skipped INTEGER NOT NULL DEFAULT 0
    """,
    """
    ALTER TABLE infrastructure_poll_runs
    ADD COLUMN IF NOT EXISTS sites_recovered INTEGER NOT NULL DEFAULT 0
    """,
    """
    ALTER TABLE infrastructure_poll_runs
    ADD COLUMN IF NOT EXISTS emails_sent INTEGER NOT NULL DEFAULT 0
    """,
    """
    ALTER TABLE infrastructure_poll_runs
    ADD COLUMN IF NOT EXISTS email_sites INTEGER NOT NULL DEFAULT 0
    """,
    """
    ALTER TABLE infrastructure_poll_runs
    ADD COLUMN IF NOT EXISTS error_count INTEGER NOT NULL DEFAULT 0
    """,
    """
    ALTER TABLE infrastructure_poll_runs
    ADD COLUMN IF NOT EXISTS error_summary TEXT
    """,
    """
    ALTER TABLE infrastructure_poll_runs
    ADD COLUMN IF NOT EXISTS started_at TIMESTAMPTZ NOT NULL DEFAULT now()
    """,
    """
    ALTER TABLE infrastructure_poll_runs
    ADD COLUMN IF NOT EXISTS completed_at TIMESTAMPTZ
    """,
    """
    ALTER TABLE infrastructure_poll_runs
    ADD COLUMN IF NOT EXISTS duration_seconds NUMERIC
    """,
)

# The external ITOM system can return opaque identifiers larger than signed
# 64-bit BIGINT. Preserve sync_run_id as text.
SYNC_RUN_ID_MIGRATION = """
DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = current_schema()
          AND table_name = 'infrastructure_site_incidents'
          AND column_name = 'sync_run_id'
          AND data_type <> 'text'
    ) THEN
        ALTER TABLE infrastructure_site_incidents
        ALTER COLUMN sync_run_id TYPE TEXT
        USING sync_run_id::text;
    END IF;
END $$
"""


def _json_default(value: Any) -> Any:
    """Convert PostgreSQL/Python values into JSON-safe values."""
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


class InfrastructureStateRepository:
    """Read and write Infrastructure Agent state in the TechAdmin database."""

    def ensure_schema(self) -> None:
        """Create tables and apply all additive migrations safely."""
        with SessionLocal() as db:
            db.execute(text(INCIDENT_DDL))
            db.execute(text(POLL_RUN_DDL))

            for migration in POLL_RUN_MIGRATIONS:
                db.execute(text(migration))

            db.execute(text(SYNC_RUN_ID_MIGRATION))
            db.execute(text(POLL_RUN_INDEX_DDL))
            db.execute(text(INCIDENT_STATUS_INDEX_DDL))
            db.execute(text(INCIDENT_UPDATED_INDEX_DDL))
            db.commit()

    def start_poll_run(self, trigger_type: str) -> int:
        """Create a running audit record and return its numeric ID."""
        normalized_trigger = str(trigger_type or "manual").strip().casefold()
        if normalized_trigger not in {"manual", "scheduled", "startup"}:
            normalized_trigger = "manual"

        self.ensure_schema()

        with SessionLocal() as db:
            run_id = db.execute(
                text(
                    """
                    INSERT INTO infrastructure_poll_runs (
                        trigger_type,
                        status,
                        started_at
                    ) VALUES (
                        :trigger_type,
                        'running',
                        now()
                    )
                    RETURNING id
                    """
                ),
                {"trigger_type": normalized_trigger},
            ).scalar_one()
            db.commit()
            return int(run_id)

    def complete_poll_run(
        self,
        run_id: int,
        *,
        status: str,
        summary: dict[str, Any],
        source_sync_run_id: str | None,
        error_summary: str | None = None,
    ) -> None:
        """Complete one poll-history row with execution counters."""
        errors = summary.get("errors") or []
        if error_summary is None and errors:
            error_summary = "\n".join(str(item) for item in errors[:20])

        normalized_status = str(status or "completed").strip().casefold()
        if normalized_status not in {
            "completed",
            "completed_with_errors",
            "failed",
        }:
            normalized_status = "completed_with_errors"

        self.ensure_schema()

        with SessionLocal() as db:
            db.execute(
                text(
                    """
                    UPDATE infrastructure_poll_runs SET
                        status = :status,
                        source_sync_run_id = :source_sync_run_id,
                        alerts_found = :alerts_found,
                        tickets_attempted = :tickets_attempted,
                        tickets_created = :tickets_created,
                        sites_skipped = :sites_skipped,
                        sites_recovered = :sites_recovered,
                        emails_sent = :emails_sent,
                        email_sites = :email_sites,
                        error_count = :error_count,
                        error_summary = :error_summary,
                        completed_at = now(),
                        duration_seconds = EXTRACT(
                            EPOCH FROM (now() - started_at)
                        )
                    WHERE id = :run_id
                    """
                ),
                {
                    "run_id": int(run_id),
                    "status": normalized_status,
                    "source_sync_run_id": (
                        str(source_sync_run_id)
                        if source_sync_run_id not in (None, "")
                        else None
                    ),
                    "alerts_found": int(summary.get("alerts") or 0),
                    "tickets_attempted": int(
                        summary.get("tickets_attempted") or 0
                    ),
                    "tickets_created": int(
                        summary.get("tickets_created") or 0
                    ),
                    "sites_skipped": int(summary.get("skipped") or 0),
                    "sites_recovered": int(summary.get("recovered") or 0),
                    "emails_sent": int(summary.get("emails_sent") or 0),
                    "email_sites": int(summary.get("email_sites") or 0),
                    "error_count": len(errors),
                    "error_summary": error_summary,
                },
            )
            db.commit()

    def list_poll_runs(self, limit: int = 100) -> list[dict[str, Any]]:
        """Return newest poll executions for the UI history tab."""
        self.ensure_schema()
        safe_limit = max(1, min(int(limit), 1000))

        with SessionLocal() as db:
            rows = db.execute(
                text(
                    """
                    SELECT
                        id,
                        trigger_type,
                        status,
                        source_sync_run_id,
                        alerts_found,
                        tickets_attempted,
                        tickets_created,
                        sites_skipped,
                        sites_recovered,
                        emails_sent,
                        email_sites,
                        error_count,
                        error_summary,
                        started_at,
                        completed_at,
                        duration_seconds
                    FROM infrastructure_poll_runs
                    ORDER BY started_at DESC
                    LIMIT :limit
                    """
                ),
                {"limit": safe_limit},
            ).mappings().all()
            return [dict(row) for row in rows]

    def get(self, location_name: str) -> dict[str, Any] | None:
        """Return the current incident state for one site."""
        self.ensure_schema()

        with SessionLocal() as db:
            row = db.execute(
                text(
                    """
                    SELECT *
                    FROM infrastructure_site_incidents
                    WHERE location_name = :location
                    """
                ),
                {"location": location_name},
            ).mappings().first()
            return dict(row) if row else None

    def should_create_ticket(
        self,
        alert: InfrastructureSiteAlert,
    ) -> tuple[bool, str]:
        """Apply site-level deduplication and escalation rules."""
        current = self.get(alert.location_name)

        if not current:
            return True, "new_alert"

        if current.get("current_status") == "recovered":
            return True, "recurrence"

        if current.get("priority") == "P2" and alert.priority == "P1":
            return True, "priority_escalation"

        if (
            not current.get("ticket_id")
            and current.get("ticket_status") != "accepted"
        ):
            return True, "previous_ticket_not_created"

        return False, "existing_active_incident"

    def upsert_detection(
        self,
        alert: InfrastructureSiteAlert,
        *,
        description: str,
        prompt: str,
    ) -> None:
        """Insert or refresh the latest state for one affected site."""
        self.ensure_schema()
        payload = json.dumps(alert.as_dict(), default=_json_default)

        with SessionLocal() as db:
            db.execute(
                text(
                    """
                    INSERT INTO infrastructure_site_incidents (
                        location_name,
                        current_status,
                        priority,
                        sync_run_id,
                        site_score,
                        site_reason,
                        affected_count,
                        ticket_description,
                        solarwinds_prompt,
                        detail_json,
                        first_detected_at,
                        last_detected_at,
                        updated_at,
                        recovered_at
                    ) VALUES (
                        :location,
                        :status,
                        :priority,
                        :sync_run_id,
                        :site_score,
                        :site_reason,
                        :affected_count,
                        :description,
                        :prompt,
                        CAST(:detail_json AS jsonb),
                        now(),
                        now(),
                        now(),
                        NULL
                    )
                    ON CONFLICT (location_name) DO UPDATE SET
                        current_status = EXCLUDED.current_status,
                        priority = EXCLUDED.priority,
                        sync_run_id = EXCLUDED.sync_run_id,
                        site_score = EXCLUDED.site_score,
                        site_reason = EXCLUDED.site_reason,
                        affected_count = EXCLUDED.affected_count,
                        ticket_description = EXCLUDED.ticket_description,
                        solarwinds_prompt = EXCLUDED.solarwinds_prompt,
                        detail_json = EXCLUDED.detail_json,
                        last_detected_at = now(),
                        recovered_at = NULL,
                        updated_at = now()
                    """
                ),
                {
                    "location": alert.location_name,
                    "status": alert.site_status,
                    "priority": alert.priority,
                    "sync_run_id": str(alert.sync_run_id),
                    "site_score": alert.site_score,
                    "site_reason": alert.site_reason,
                    "affected_count": alert.affected_count,
                    "description": description,
                    "prompt": prompt,
                    "detail_json": payload,
                },
            )
            db.commit()

    def record_ticket(
        self,
        location_name: str,
        *,
        success: bool,
        ticket_id: str | None,
        message: str,
    ) -> None:
        """Persist the site-level iEngage result."""
        self.ensure_schema()

        with SessionLocal() as db:
            db.execute(
                text(
                    """
                    UPDATE infrastructure_site_incidents SET
                        ticket_status = :status,
                        ticket_id = COALESCE(:ticket_id, ticket_id),
                        ticket_message = :message,
                        last_ticketed_at = CASE
                            WHEN :success THEN now()
                            ELSE last_ticketed_at
                        END,
                        updated_at = now()
                    WHERE location_name = :location
                    """
                ),
                {
                    "status": (
                        "created"
                        if success and ticket_id
                        else "accepted"
                        if success
                        else "failed"
                    ),
                    "ticket_id": ticket_id,
                    "message": message,
                    "success": bool(success),
                    "location": location_name,
                },
            )
            db.commit()

    def record_email(
        self,
        location_name: str,
        success: bool,
        message: str,
    ) -> None:
        """Record the consolidated-email result against each included site."""
        self.ensure_schema()

        with SessionLocal() as db:
            db.execute(
                text(
                    """
                    UPDATE infrastructure_site_incidents SET
                        email_status = :status,
                        email_message = :message,
                        last_emailed_at = CASE
                            WHEN :success THEN now()
                            ELSE last_emailed_at
                        END,
                        updated_at = now()
                    WHERE location_name = :location
                    """
                ),
                {
                    "status": "sent" if success else "failed",
                    "message": message,
                    "success": bool(success),
                    "location": location_name,
                },
            )
            db.commit()

    def mark_recovered_except(self, active_locations: set[str]) -> int:
        """Mark sites absent from the latest P1/P2 set as recovered."""
        self.ensure_schema()

        with SessionLocal() as db:
            if active_locations:
                result = db.execute(
                    text(
                        """
                        UPDATE infrastructure_site_incidents SET
                            current_status = 'recovered',
                            recovered_at = now(),
                            updated_at = now()
                        WHERE current_status <> 'recovered'
                          AND NOT (location_name = ANY(:locations))
                        """
                    ),
                    {"locations": list(active_locations)},
                )
            else:
                result = db.execute(
                    text(
                        """
                        UPDATE infrastructure_site_incidents SET
                            current_status = 'recovered',
                            recovered_at = now(),
                            updated_at = now()
                        WHERE current_status <> 'recovered'
                        """
                    )
                )

            db.commit()
            return int(result.rowcount or 0)

    def list_incidents(self, limit: int = 500) -> list[dict[str, Any]]:
        """Return current site incident state for the Infrastructure UI."""
        self.ensure_schema()
        safe_limit = max(1, min(int(limit), 5000))

        with SessionLocal() as db:
            rows = db.execute(
                text(
                    """
                    SELECT *
                    FROM infrastructure_site_incidents
                    ORDER BY
                        CASE current_status
                            WHEN 'critical' THEN 1
                            WHEN 'warning' THEN 2
                            ELSE 3
                        END,
                        CASE priority
                            WHEN 'P1' THEN 1
                            WHEN 'P2' THEN 2
                            ELSE 3
                        END,
                        updated_at DESC,
                        location_name
                    LIMIT :limit
                    """
                ),
                {"limit": safe_limit},
            ).mappings().all()
            return [dict(row) for row in rows]
