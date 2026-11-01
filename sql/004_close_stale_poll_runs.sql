UPDATE infrastructure_poll_runs
SET status = 'failed',
    completed_at = COALESCE(completed_at, now()),
    duration_seconds = COALESCE(duration_seconds, EXTRACT(EPOCH FROM (now() - started_at))),
    error_count = CASE WHEN error_count = 0 THEN 1 ELSE error_count END,
    error_summary = COALESCE(NULLIF(error_summary, ''),
        'Application stopped or restarted before this poll completed.')
WHERE status = 'running'
  AND started_at < now() - INTERVAL '30 minutes';
