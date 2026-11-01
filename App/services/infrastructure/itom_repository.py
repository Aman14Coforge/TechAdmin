"""Queries for the latest site-health evidence in the external ITOM database."""
from __future__ import annotations

import os
from collections import defaultdict
from typing import Any

from psycopg import sql

from App.db.itom_connection import itom_connection
from App.services.infrastructure.models import (
    InfrastructureDevice,
    InfrastructureSiteAlert,
)


SUMMARY_SQL = """
WITH latest_sync AS (
    SELECT id, completed_at
    FROM {schema}.sync_runs
    WHERE status = 'SUCCESS'
    ORDER BY completed_at DESC NULLS LAST, id DESC
    LIMIT 1
)
SELECT
    l.id::text AS sync_run_id,
    s.location_name,
    s.data->'scores'->'combined'->>'status' AS site_status,
    (s.data->'scores'->'combined'->>'value')::numeric AS site_score,
    COUNT(*) AS total_devices,
    COUNT(*) FILTER (WHERE i.status IN ('Up','Compliant')) AS healthy,
    COUNT(*) FILTER (WHERE i.status IN ('Down','Critical')) AS critical_devices,
    COUNT(*) FILTER (WHERE i.status IN ('Warning','NonCompliant')) AS degraded,
    COUNT(*) FILTER (
        WHERE i.status IN ('Unmanaged','Unknown','ConfigManager','InGracePeriod')
    ) AS not_assessed,
    ROUND(
        100.0 * COUNT(*) FILTER (WHERE i.status IN ('Up','Compliant'))
        / NULLIF(COUNT(*), 0),
        1
    ) AS healthy_pct
FROM {schema}.geographic_score_snapshots AS s
JOIN latest_sync AS l ON l.id = s.sync_run_id
JOIN {schema}.geographic_score_inventory AS i ON i.snapshot_id = s.id
GROUP BY l.id, s.location_name, site_status, site_score
"""

DETAIL_SQL = """
WITH latest_sync AS (
    SELECT id, completed_at
    FROM {schema}.sync_runs
    WHERE status = 'SUCCESS'
    ORDER BY completed_at DESC NULLS LAST, id DESC
    LIMIT 1
)
SELECT
    l.id::text AS sync_run_id,
    s.location_name,
    s.match_level,
    s.data->'scores'->'combined'->>'status' AS site_status,
    (s.data->'scores'->'combined'->>'value')::numeric AS site_score,
    s.data->'scores'->'combined'->>'reason' AS site_reason,
    CASE lower(s.data->'scores'->'combined'->>'status')
        WHEN 'critical' THEN 'P1'
        WHEN 'warning' THEN 'P2'
    END AS priority,
    i.source_system,
    i.name AS device_name,
    i.ci_type,
    i.status AS device_status,
    i.source_location,
    (l.completed_at AT TIME ZONE 'Asia/Kolkata') AS sync_completed_ist,
    (s.recorded_at AT TIME ZONE 'Asia/Kolkata') AS score_calculated_ist,
    (i.last_sync_time AT TIME ZONE 'Asia/Kolkata') AS device_last_pulled_ist,
    (
        NULLIF(NULLIF(i.checkin_at_source, ''), '0001-01-01T00:00:00Z')::timestamptz
        AT TIME ZONE 'Asia/Kolkata'
    ) AS device_last_seen_ist,
    date_trunc('second', now() - l.completed_at)::text AS data_age,
    date_trunc(
        'second',
        now() - NULLIF(
            NULLIF(i.checkin_at_source, ''),
            '0001-01-01T00:00:00Z'
        )::timestamptz
    )::text AS device_silent_for
FROM {schema}.geographic_score_snapshots AS s
JOIN latest_sync AS l ON l.id = s.sync_run_id
JOIN {schema}.geographic_score_inventory AS i ON i.snapshot_id = s.id
WHERE lower(s.data->'scores'->'combined'->>'status') IN ('critical', 'warning')
  AND (
        (upper(i.source_system) = 'SOLARWINDS' AND i.status IN ('Down','Critical','Warning'))
     OR (upper(i.source_system) = 'INTUNE' AND i.status IN ('NonCompliant','Unknown'))
  )
ORDER BY
    CASE i.status
        WHEN 'Down' THEN 1
        WHEN 'Critical' THEN 2
        WHEN 'Warning' THEN 3
        WHEN 'NonCompliant' THEN 4
        ELSE 5
    END,
    s.location_name,
    i.source_system,
    i.name
"""


class ITOMSiteRepository:
    def __init__(self) -> None:
        schema = os.getenv("ITOM_DB_SCHEMA", "public").strip() or "public"
        if not schema.replace("_", "").isalnum():
            raise ValueError("ITOM_DB_SCHEMA contains invalid characters")
        self.schema = schema

    def latest_alerts(self) -> list[InfrastructureSiteAlert]:
        summary_query = sql.SQL(SUMMARY_SQL).format(
            schema=sql.Identifier(self.schema)
        )
        detail_query = sql.SQL(DETAIL_SQL).format(
            schema=sql.Identifier(self.schema)
        )

        with itom_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(summary_query)
                summary_rows = cursor.fetchall()
                cursor.execute(detail_query)
                detail_rows = cursor.fetchall()

        summaries: dict[str, dict[str, Any]] = {
            str(row["location_name"]): row for row in summary_rows
        }
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in detail_rows:
            grouped[str(row["location_name"])].append(row)

        alerts: list[InfrastructureSiteAlert] = []
        for location_name, rows in grouped.items():
            first = rows[0]
            summary = summaries.get(location_name, {})
            priority = str(first.get("priority") or "").upper()
            if priority not in {"P1", "P2"}:
                continue

            alerts.append(
                InfrastructureSiteAlert(
                    sync_run_id=str(first.get("sync_run_id") or ""),
                    location_name=location_name,
                    match_level=first.get("match_level"),
                    site_status=str(first.get("site_status") or "").lower(),
                    site_score=(
                        float(first["site_score"])
                        if first.get("site_score") is not None
                        else None
                    ),
                    site_reason=first.get("site_reason"),
                    priority=priority,
                    sync_completed_ist=first.get("sync_completed_ist"),
                    score_calculated_ist=first.get("score_calculated_ist"),
                    data_age=first.get("data_age"),
                    total_devices=int(summary.get("total_devices") or 0),
                    healthy=int(summary.get("healthy") or 0),
                    critical_devices=int(summary.get("critical_devices") or 0),
                    degraded=int(summary.get("degraded") or 0),
                    not_assessed=int(summary.get("not_assessed") or 0),
                    healthy_pct=(
                        float(summary["healthy_pct"])
                        if summary.get("healthy_pct") is not None
                        else None
                    ),
                    devices=[
                        InfrastructureDevice(
                            source_system=str(row.get("source_system") or ""),
                            device_name=str(row.get("device_name") or ""),
                            ci_type=row.get("ci_type"),
                            device_status=str(row.get("device_status") or ""),
                            source_location=row.get("source_location"),
                            device_last_pulled_ist=row.get("device_last_pulled_ist"),
                            device_last_seen_ist=row.get("device_last_seen_ist"),
                            device_silent_for=row.get("device_silent_for"),
                        )
                        for row in rows
                    ],
                )
            )

        return sorted(
            alerts,
            key=lambda item: (
                item.priority != "P1",
                item.location_name.casefold(),
            ),
        )
