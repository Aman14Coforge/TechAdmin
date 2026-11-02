-- Query 2 (TechAdmin Infrastructure Agent): per-location site score and device health
-- counts from the latest successful sync. One row per location.
WITH latest_sync AS (
    SELECT id FROM public.sync_runs
    WHERE status = 'SUCCESS'
    ORDER BY completed_at DESC NULLS LAST, id DESC LIMIT 1
)
SELECT
    s.location_name,
    s.data->'scores'->'combined'->>'status'             AS site_status,
    (s.data->'scores'->'combined'->>'value')::numeric   AS site_score,

    COUNT(*)                                                       AS total_devices,
    COUNT(*) FILTER (WHERE i.status IN ('Up','Compliant'))         AS healthy,
    COUNT(*) FILTER (WHERE i.status IN ('Down','Critical'))        AS critical_devices,
    COUNT(*) FILTER (WHERE i.status IN ('Warning','NonCompliant')) AS degraded,
    COUNT(*) FILTER (WHERE i.status IN
        ('Unmanaged','Unknown','ConfigManager','InGracePeriod'))   AS not_assessed,

    ROUND(100.0 * COUNT(*) FILTER (WHERE i.status IN ('Up','Compliant'))
                / NULLIF(COUNT(*), 0), 1)                          AS healthy_pct
FROM public.geographic_score_snapshots      s
JOIN latest_sync                            l ON l.id = s.sync_run_id
JOIN public.geographic_score_inventory      i ON i.snapshot_id = s.id
GROUP BY 1, 2, 3
ORDER BY critical_devices DESC, healthy_pct;
