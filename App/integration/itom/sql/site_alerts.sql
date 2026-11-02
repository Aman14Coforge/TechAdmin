-- Main ITOM query (TechAdmin): P1/P2 sites from the latest successful sync,
-- with their problem SolarWinds and Intune devices. Times shown in IST.
-- DB: itom_db @ 172.18.51.38:5432, read-only user itom_ro.
WITH latest_sync AS (
    SELECT id, completed_at
    FROM public.sync_runs
    WHERE status = 'SUCCESS'
    ORDER BY completed_at DESC NULLS LAST, id DESC
    LIMIT 1
)
SELECT
    -- site
    s.location_name,
    s.match_level,
    s.data->'scores'->'combined'->>'status'           AS site_status,
    (s.data->'scores'->'combined'->>'value')::numeric AS site_score,
    s.data->'scores'->'combined'->>'reason'           AS site_reason,
    CASE s.data->'scores'->'combined'->>'status'
         WHEN 'critical' THEN 'P1'
         WHEN 'warning'  THEN 'P2'
    END                                               AS priority,

    -- device
    i.source_system,
    i.name        AS device_name,
    i.ci_type,
    i.status      AS device_status,
    i.source_location,

    -- timing, in IST
    (l.completed_at   AT TIME ZONE 'Asia/Kolkata')    AS sync_completed_ist,
    (s.recorded_at    AT TIME ZONE 'Asia/Kolkata')    AS score_calculated_ist,
    (i.last_sync_time AT TIME ZONE 'Asia/Kolkata')    AS device_last_pulled_ist,
    (NULLIF(NULLIF(i.checkin_at_source, ''), '0001-01-01T00:00:00Z')::timestamptz
         AT TIME ZONE 'Asia/Kolkata')                 AS device_last_seen_ist,

    date_trunc('second', now() - l.completed_at)      AS data_age,
    date_trunc('second', now()
        - NULLIF(NULLIF(i.checkin_at_source, ''), '0001-01-01T00:00:00Z')::timestamptz)
                                                      AS device_silent_for

FROM public.geographic_score_snapshots      AS s
JOIN latest_sync                            AS l ON l.id = s.sync_run_id
JOIN public.geographic_score_inventory      AS i ON i.snapshot_id = s.id

WHERE s.data->'scores'->'combined'->>'status' IN ('critical', 'warning')
  AND (
        (i.source_system = 'SOLARWINDS' AND i.status IN ('Down', 'Critical', 'Warning'))
     OR (i.source_system = 'INTUNE'     AND i.status IN ('NonCompliant', 'Unknown'))
      )

ORDER BY
    CASE i.status
         WHEN 'Down'         THEN 1
         WHEN 'Critical'     THEN 2
         WHEN 'Warning'      THEN 3
         WHEN 'NonCompliant' THEN 4
         ELSE 5
    END,
    s.location_name,
    i.source_system,
    i.name;
