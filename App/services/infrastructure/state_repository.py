"""Persistence for Infrastructure Agent incident and polling state."""
from __future__ import annotations

import json
from typing import Any

from sqlalchemy import text

from App.db.connection import SessionLocal
from App.services.infrastructure.models import InfrastructureSiteAlert


DDL = """
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

# CREATE TABLE IF NOT EXISTS does not change an already-created BIGINT column.
# This idempotent migration converts it to TEXT and preserves existing values.
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


class InfrastructureStateRepository:
    def ensure_schema(self) -> None:
        with SessionLocal() as db:
            db.execute(text(DDL))
            db.execute(text(SYNC_RUN_ID_MIGRATION))
            db.commit()

    def get(self, location_name: str) -> dict[str, Any] | None:
        self.ensure_schema()
        with SessionLocal() as db:
            row = db.execute(
                text(
                    "SELECT * FROM infrastructure_site_incidents "
                    "WHERE location_name = :location"
                ),
                {"location": location_name},
            ).mappings().first()
            return dict(row) if row else None

    def should_create_ticket(
        self,
        alert: InfrastructureSiteAlert,
    ) -> tuple[bool, str]:
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
        self.ensure_schema()
        payload = json.dumps(alert.as_dict(), default=str)

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
                    "success": success,
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
                    "success": success,
                    "location": location_name,
                },
            )
            db.commit()

    def mark_recovered_except(
        self,
        active_locations: set[str],
    ) -> int:
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

    def list_incidents(
        self,
        limit: int = 500,
    ) -> list[dict[str, Any]]:
        self.ensure_schema()
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
                        updated_at DESC
                    LIMIT :limit
                    """
                ),
                {"limit": limit},
            ).mappings().all()
            return [dict(row) for row in rows]
