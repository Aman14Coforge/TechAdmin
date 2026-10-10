from __future__ import annotations
import uuid
from datetime import datetime, timezone
from sqlalchemy import DateTime, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from App.db.base import Base
from App.db.connection import DB_SCHEMA

def utc_now() -> datetime:
    return datetime.now(timezone.utc)

class SecurityAgentQuery(Base):
    __tablename__ = "security_agent_queries"
    __table_args__ = {"schema": DB_SCHEMA}
    query_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    requester_id: Mapped[str | None] = mapped_column(String(255), index=True)
    requester_name: Mapped[str | None] = mapped_column(String(255))
    query_text: Mapped[str] = mapped_column(Text)
    action: Mapped[str | None] = mapped_column(String(80), index=True)
    target: Mapped[str | None] = mapped_column(String(255), index=True)
    status: Mapped[str] = mapped_column(String(40), index=True)
    request_metadata: Mapped[dict | None] = mapped_column(JSONB)
    response_summary: Mapped[dict | None] = mapped_column(JSONB)
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
