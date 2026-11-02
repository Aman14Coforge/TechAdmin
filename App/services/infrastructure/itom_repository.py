"""Fetch exact ITOM site fields and SolarWinds-only device evidence."""
from __future__ import annotations
import os
from collections import defaultdict
from typing import Any
from psycopg import sql
from App.db.itom_connection import itom_connection
from App.services.infrastructure.models import InfrastructureDevice, InfrastructureSiteAlert

SUMMARY_SQL = """
WITH latest_sync AS (
 SELECT id, completed_at FROM {schema}.sync_runs
 WHERE status='SUCCESS' ORDER BY completed_at DESC NULLS LAST, id DESC LIMIT 1
)
SELECT l.id::text AS sync_run_id, s.location_name,
 s.data->'scores'->'combined'->>'status' AS site_status,
 (s.data->'scores'->'combined'->>'value')::numeric AS site_score,
 COUNT(*) AS total_devices,
 COUNT(*) FILTER (WHERE i.status='Up') AS healthy,
 COUNT(*) FILTER (WHERE i.status IN ('Down','Critical')) AS critical_devices,
 COUNT(*) FILTER (WHERE i.status='Warning') AS degraded,
 COUNT(*) FILTER (WHERE i.status IN ('Unknown','Unmanaged')) AS not_assessed,
 ROUND(100.0 * COUNT(*) FILTER (WHERE i.status='Up') / NULLIF(COUNT(*),0),1) AS healthy_pct
FROM {schema}.geographic_score_snapshots s
JOIN latest_sync l ON l.id=s.sync_run_id
JOIN {schema}.geographic_score_inventory i ON i.snapshot_id=s.id
WHERE upper(i.source_system)='SOLARWINDS'
GROUP BY l.id,s.location_name,site_status,site_score
"""

DETAIL_SQL = """
WITH latest_sync AS (
 SELECT id, completed_at FROM {schema}.sync_runs
 WHERE status='SUCCESS' ORDER BY completed_at DESC NULLS LAST, id DESC LIMIT 1
)
SELECT l.id::text AS sync_run_id, s.location_name, s.match_level,
 s.data->'scores'->'combined'->>'status' AS site_status,
 (s.data->'scores'->'combined'->>'value')::numeric AS site_score,
 s.data->'scores'->'combined'->>'reason' AS site_reason,
 CASE lower(s.data->'scores'->'combined'->>'status')
  WHEN 'critical' THEN 'P1' WHEN 'warning' THEN 'P2' END AS priority,
 i.source_system, i.name AS device_name, i.ci_type, i.status AS device_status,
 i.source_location,
 (l.completed_at AT TIME ZONE 'Asia/Kolkata') AS sync_completed_ist,
 (s.recorded_at AT TIME ZONE 'Asia/Kolkata') AS score_calculated_ist,
 (i.last_sync_time AT TIME ZONE 'Asia/Kolkata') AS device_last_pulled_ist,
 (NULLIF(NULLIF(i.checkin_at_source,''),'0001-01-01T00:00:00Z')::timestamptz
   AT TIME ZONE 'Asia/Kolkata') AS device_last_seen_ist,
 date_trunc('second',now()-l.completed_at)::text AS data_age,
 date_trunc('second',now()-NULLIF(NULLIF(i.checkin_at_source,''),'0001-01-01T00:00:00Z')::timestamptz)::text AS device_silent_for
FROM {schema}.geographic_score_snapshots s
JOIN latest_sync l ON l.id=s.sync_run_id
JOIN {schema}.geographic_score_inventory i ON i.snapshot_id=s.id
WHERE lower(s.data->'scores'->'combined'->>'status') IN ('critical','warning')
 AND upper(i.source_system)='SOLARWINDS'
 AND i.status IN ('Down','Critical','Warning')
ORDER BY CASE i.status WHEN 'Down' THEN 1 WHEN 'Critical' THEN 2 WHEN 'Warning' THEN 3 ELSE 4 END,
 s.location_name,i.name
"""

class ITOMSiteRepository:
    def __init__(self) -> None:
        schema=os.getenv("ITOM_DB_SCHEMA","public").strip() or "public"
        if not schema.replace("_","").isalnum(): raise ValueError("Invalid ITOM_DB_SCHEMA")
        self.schema=schema

    def latest_alerts(self) -> list[InfrastructureSiteAlert]:
        with itom_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(sql.SQL(SUMMARY_SQL).format(schema=sql.Identifier(self.schema)))
                summaries={str(r["location_name"]):r for r in cursor.fetchall()}
                cursor.execute(sql.SQL(DETAIL_SQL).format(schema=sql.Identifier(self.schema)))
                details=cursor.fetchall()
        grouped: dict[str,list[dict[str,Any]]]=defaultdict(list)
        for row in details: grouped[str(row["location_name"])].append(row)
        alerts=[]
        for location,rows in grouped.items():
            first=rows[0]; summary=summaries.get(location,{}); priority=str(first.get("priority") or "").upper()
            if priority not in {"P1","P2"}: continue
            alerts.append(InfrastructureSiteAlert(
                str(first.get("sync_run_id") or ""),location,first.get("match_level"),
                str(first.get("site_status") or "").lower(),
                float(first["site_score"]) if first.get("site_score") is not None else None,
                first.get("site_reason"),priority,first.get("sync_completed_ist"),
                first.get("score_calculated_ist"),first.get("data_age"),
                int(summary.get("total_devices") or 0),int(summary.get("healthy") or 0),
                int(summary.get("critical_devices") or 0),int(summary.get("degraded") or 0),
                int(summary.get("not_assessed") or 0),
                float(summary["healthy_pct"]) if summary.get("healthy_pct") is not None else None,
                [InfrastructureDevice("SOLARWINDS",str(r.get("device_name") or ""),r.get("ci_type"),
                 str(r.get("device_status") or ""),r.get("source_location"),r.get("device_last_pulled_ist"),
                 r.get("device_last_seen_ist"),r.get("device_silent_for")) for r in rows]
            ))
        return sorted(alerts,key=lambda a:(a.priority!="P1",a.location_name.casefold()))

    def get_site_alert(self, location_name: str) -> InfrastructureSiteAlert | None:
        wanted=str(location_name or "").strip().casefold()
        return next((a for a in self.latest_alerts() if a.location_name.casefold()==wanted),None)
