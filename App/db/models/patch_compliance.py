from __future__ import annotations
import uuid
from datetime import date, datetime, timezone
from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from App.db.base import Base
from App.db.connection import DB_SCHEMA

def utc_now() -> datetime:
    return datetime.now(timezone.utc)

class PatchScanRun(Base):
    __tablename__ = "patch_scan_runs"
    __table_args__ = (Index("ix_patch_scan_date_started", "scan_date", "started_at"), {"schema": DB_SCHEMA})
    scan_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    scan_date: Mapped[date] = mapped_column(Date, index=True)
    source: Mapped[str] = mapped_column(String(40), default="MANUAL")
    status: Mapped[str] = mapped_column(String(30), default="RUNNING")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    noncompliant_devices: Mapped[int] = mapped_column(Integer, default=0)
    vulnerable_devices: Mapped[int] = mapped_column(Integer, default=0)
    resolved_devices: Mapped[int] = mapped_column(Integer, default=0)
    eligible_devices: Mapped[int] = mapped_column(Integer, default=0)
    tickets_created: Mapped[int] = mapped_column(Integer, default=0)
    errors: Mapped[list | None] = mapped_column(JSONB)

class PatchDeviceState(Base):
    __tablename__ = "patch_device_states"
    __table_args__ = (UniqueConstraint("discovery_id"), Index("ix_patch_active_days", "is_active", "consecutive_days"), {"schema": DB_SCHEMA})
    state_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    discovery_id: Mapped[str] = mapped_column(String(255), nullable=False)
    device_name: Mapped[str] = mapped_column(String(255), index=True)
    display_name: Mapped[str | None] = mapped_column(String(255))
    first_seen_date: Mapped[date] = mapped_column(Date)
    last_seen_date: Mapped[date] = mapped_column(Date)
    consecutive_days: Mapped[int] = mapped_column(Integer, default=1)
    total_observed_days: Mapped[int] = mapped_column(Integer, default=1)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    missing_patch_count: Mapped[int] = mapped_column(Integer, default=0)
    risk_score: Mapped[float | None] = mapped_column(Float)
    notifications: Mapped[list | None] = mapped_column(JSONB)
    ticket_status: Mapped[str] = mapped_column(String(40), default="NOT_ELIGIBLE")
    ticket_reference: Mapped[str | None] = mapped_column(String(255))
    ticket_created_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_scan_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey(f"{DB_SCHEMA}.patch_scan_runs.scan_id"))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

class PatchDeviceObservation(Base):
    __tablename__ = "patch_device_observations"
    __table_args__ = (UniqueConstraint("scan_date", "discovery_id"), Index("ix_patch_obs_date_name", "scan_date", "device_name"), {"schema": DB_SCHEMA})
    observation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    scan_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey(f"{DB_SCHEMA}.patch_scan_runs.scan_id"))
    scan_date: Mapped[date] = mapped_column(Date)
    discovery_id: Mapped[str] = mapped_column(String(255))
    device_name: Mapped[str] = mapped_column(String(255))
    missing_patch_count: Mapped[int] = mapped_column(Integer, default=0)
    risk_score: Mapped[float | None] = mapped_column(Float)
    last_scanned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ip_address: Mapped[str | None] = mapped_column(String(100))
    os_name: Mapped[str | None] = mapped_column(String(255))
    notifications: Mapped[list | None] = mapped_column(JSONB)
    telemetry: Mapped[dict | None] = mapped_column(JSONB)

class PatchFinding(Base):
    __tablename__ = "patch_findings"
    __table_args__ = (UniqueConstraint("scan_date", "discovery_id", "evidence_key"), Index("ix_patch_find_device_date", "discovery_id", "scan_date"), {"schema": DB_SCHEMA})
    finding_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    scan_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey(f"{DB_SCHEMA}.patch_scan_runs.scan_id"))
    scan_date: Mapped[date] = mapped_column(Date)
    discovery_id: Mapped[str] = mapped_column(String(255))
    device_name: Mapped[str] = mapped_column(String(255))
    evidence_key: Mapped[str] = mapped_column(String(350))
    evidence_type: Mapped[str] = mapped_column(String(40))
    patch_name: Mapped[str | None] = mapped_column(Text)
    patch_id: Mapped[str | None] = mapped_column(String(255))
    notification_id: Mapped[str | None] = mapped_column(String(255))
    kb_number: Mapped[str | None] = mapped_column(String(100))
    vendor_name: Mapped[str | None] = mapped_column(String(255))
    patch_status: Mapped[str | None] = mapped_column(String(50))
    severity: Mapped[int | None] = mapped_column(Integer)
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deployment_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    deployment_status: Mapped[str | None] = mapped_column(String(100))
    return_code: Mapped[str | None] = mapped_column(String(150))
    failure_reason: Mapped[str | None] = mapped_column(Text)
    raw_evidence: Mapped[dict | None] = mapped_column(JSONB)

class PatchTicket(Base):
    __tablename__ = "patch_tickets"
    __table_args__ = (UniqueConstraint("discovery_id", "episode_first_seen"), Index("ix_patch_ticket_status", "status"), {"schema": DB_SCHEMA})
    ticket_row_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    discovery_id: Mapped[str] = mapped_column(String(255))
    device_name: Mapped[str] = mapped_column(String(255))
    episode_first_seen: Mapped[date] = mapped_column(Date)
    request_mode: Mapped[str] = mapped_column(String(30))
    requested_by: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(40))
    external_ticket_id: Mapped[str | None] = mapped_column(String(255))
    request_payload: Mapped[dict | None] = mapped_column(JSONB)
    response_summary: Mapped[str | None] = mapped_column(Text)
    error_message: Mapped[str | None] = mapped_column(Text)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

class PatchScanClassificationSummary(Base):
    __tablename__ = "patch_scan_classification_summaries"
    __table_args__ = ({"schema": DB_SCHEMA},)
    summary_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    scan_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, unique=True)
    scan_date: Mapped[date] = mapped_column(Date, nullable=False)
    raw_missing_patch_records: Mapped[int] = mapped_column(Integer, default=0)
    active_non_compliant_devices: Mapped[int] = mapped_column(Integer, default=0)
    persistent_14_devices: Mapped[int] = mapped_column(Integer, default=0)
    stale_reporting_devices: Mapped[int] = mapped_column(Integer, default=0)
    unknown_freshness_devices: Mapped[int] = mapped_column(Integer, default=0)
    resolved_devices: Mapped[int] = mapped_column(Integer, default=0)
    ticket_eligible_devices: Mapped[int] = mapped_column(Integer, default=0)
    freshness_threshold_days: Mapped[int] = mapped_column(Integer, default=7)
    successful_snapshots_available: Mapped[int] = mapped_column(Integer, default=0)
    required_successful_snapshots: Mapped[int] = mapped_column(Integer, default=14)
    calculation_status: Mapped[str] = mapped_column(String(30), default="RUNNING")
    calculation_error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_seconds: Mapped[float | None] = mapped_column(Float)

class PatchComplianceClassification(Base):
    __tablename__ = "patch_compliance_classifications"
    __table_args__ = (UniqueConstraint("scan_date", "discovery_id"), {"schema": DB_SCHEMA})
    classification_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    scan_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    scan_date: Mapped[date] = mapped_column(Date, nullable=False)
    discovery_id: Mapped[str] = mapped_column(String(255), nullable=False)
    device_name: Mapped[str] = mapped_column(String(255), nullable=False)
    compliance_category: Mapped[str] = mapped_column(String(40), nullable=False)
    freshness_status: Mapped[str] = mapped_column(String(30), nullable=False)
    inclusion_reason: Mapped[str | None] = mapped_column(Text)
    last_scanned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    scan_age_days: Mapped[int | None] = mapped_column(Integer)
    missing_patch_count: Mapped[int] = mapped_column(Integer, default=0)
    risk_score: Mapped[float | None] = mapped_column(Float)
    successful_snapshot_days_14: Mapped[int] = mapped_column(Integer, default=0)
    required_snapshot_days_14: Mapped[int] = mapped_column(Integer, default=14)
    persistent_14_days: Mapped[bool] = mapped_column(Boolean, default=False)
    assigned_policy: Mapped[str | None] = mapped_column(String(255))
    platform: Mapped[str | None] = mapped_column(String(100))
    os_name: Mapped[str | None] = mapped_column(String(255))
    ip_address: Mapped[str | None] = mapped_column(String(100))
    management_sources: Mapped[list | None] = mapped_column(JSONB)
    security_critical: Mapped[int] = mapped_column(Integer, default=0)
    security_important: Mapped[int] = mapped_column(Integer, default=0)
    security_moderate: Mapped[int] = mapped_column(Integer, default=0)
    security_low: Mapped[int] = mapped_column(Integer, default=0)
    exploited_missing_patches: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ticket_status: Mapped[str | None] = mapped_column(String(40))
    ticket_reference: Mapped[str | None] = mapped_column(String(255))
    calculated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

# Existing batch models retained.
class PatchTicketBatch(Base):
    __tablename__ = "patch_ticket_batches"
    __table_args__ = (Index("ix_patch_batch_status", "status", "created_at"), {"schema": DB_SCHEMA})
    batch_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    scope: Mapped[str] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(30), default="QUEUED")
    requested_by: Mapped[str | None] = mapped_column(String(255))
    reason: Mapped[str | None] = mapped_column(Text)
    total_items: Mapped[int] = mapped_column(Integer, default=0)
    processed_items: Mapped[int] = mapped_column(Integer, default=0)
    created_count: Mapped[int] = mapped_column(Integer, default=0)
    skipped_count: Mapped[int] = mapped_column(Integer, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

class PatchTicketBatchItem(Base):
    __tablename__ = "patch_ticket_batch_items"
    __table_args__ = (UniqueConstraint("batch_id", "discovery_id"), Index("ix_patch_batch_item_status", "batch_id", "status"), {"schema": DB_SCHEMA})
    item_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    batch_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey(f"{DB_SCHEMA}.patch_ticket_batches.batch_id"))
    discovery_id: Mapped[str] = mapped_column(String(255))
    device_name: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(30), default="QUEUED")
    ticket_id: Mapped[str | None] = mapped_column(String(255))
    error_message: Mapped[str | None] = mapped_column(Text)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)
