CREATE INDEX IF NOT EXISTS ix_patch_observation_date_missing
ON techadmin.patch_device_observations (scan_date, missing_patch_count DESC);

CREATE INDEX IF NOT EXISTS ix_patch_observation_date_device
ON techadmin.patch_device_observations (scan_date, device_name);

CREATE INDEX IF NOT EXISTS ix_patch_state_active_days
ON techadmin.patch_device_states (is_active, consecutive_days DESC)
WHERE is_active = true;

CREATE INDEX IF NOT EXISTS ix_patch_state_device_name_lower
ON techadmin.patch_device_states (LOWER(device_name));

CREATE INDEX IF NOT EXISTS ix_patch_findings_date_discovery_type
ON techadmin.patch_findings (scan_date, discovery_id, evidence_type);
