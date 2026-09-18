"""
SQLAlchemy model for the TechAdmin operation_executions table.
Author: Amit Bhagat

One row per actual API, script or job execution attempt, as defined in section
G of the RDBMS Audit and Operation Tracking design.

The distinction that matters, from section 7 of that document:

    operation_requests    what the user asked for
    operation_executions  what the system actually attempted

A single request can have several execution rows when a retry occurs. Failed
attempts are preserved rather than overwritten, so the history stays readable:

    Request 123
      attempt 1: FAILED    - access token expired
      attempt 2: SUCCEEDED

This model maps an existing table. It defines exactly the columns listed in
section G and adds none of its own, and it is deliberately not registered in
create_tables.py because the table already exists.

Security note. As with operation_requests, nothing here holds a credential:
result_summary and error_message are sanitized before they are written, and a
temporary password or access token must never reach this table.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from App.db.base import Base
from App.db.connection import DB_SCHEMA


def utc_now() -> datetime:
    """Return the current timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


# Execution statuses from section G.
EXECUTION_RUNNING = "RUNNING"
EXECUTION_SUCCEEDED = "SUCCEEDED"
EXECUTION_FAILED = "FAILED"
EXECUTION_TIMED_OUT = "TIMED_OUT"
EXECUTION_CANCELLED = "CANCELLED"


class OperationExecution(Base):
    """One execution attempt against a TechAdmin operation request."""

    __tablename__ = "operation_executions"
    __table_args__ = {"schema": DB_SCHEMA}

    execution_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        nullable=False,
    )

    # The parent request. This is the correlation ID that ties the execution
    # back to the request, the approval and the application log.
    request_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{DB_SCHEMA}.operation_requests.request_id"),
        nullable=False,
        index=True,
    )

    # API, SCRIPT or JOB.
    execution_type: Mapped[str] = mapped_column(String(30), nullable=False)

    # The Graph tool, PowerShell script or job that ran.
    executor_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    executor_version: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # The machine that ran it. Useful once execution moves off one developer
    # laptop and onto several runners.
    executor_host: Mapped[str | None] = mapped_column(String(255), nullable=True)

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        server_default=text("CURRENT_TIMESTAMP"),
    )

    finished_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    execution_status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default=EXECUTION_RUNNING,
        index=True,
    )

    # Populated for API execution.
    http_status_code: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Populated for script execution.
    process_exit_code: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Graph request ID, process ID or job ID.
    external_reference_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )

    duration_ms: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

    # Sanitized. Never the result payload itself, which can carry a password.
    result_summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    error_code: Mapped[str | None] = mapped_column(String(150), nullable=True)

    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    retry_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default=text("0"),
    )

    def __repr__(self) -> str:
        """Concise representation. Carries no credentials."""
        return (
            "OperationExecution("
            f"execution_id='{self.execution_id}', "
            f"request_id='{self.request_id}', "
            f"status='{self.execution_status}', "
            f"duration_ms={self.duration_ms}"
            ")"
        )
