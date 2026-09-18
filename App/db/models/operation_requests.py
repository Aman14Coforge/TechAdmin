# """
# SQLAlchemy model for the TechAdmin operation_requests table.
# Author: Amit Bhagat

# One row per business request submitted to TechAdmin. The request_id is the
# end-to-end correlation ID described in section E of the RDBMS Audit and
# Operation Tracking design: the same value travels through the application log,
# the agent decision, the workflow and the execution record.

# The physical PostgreSQL table represented by this model is:

#     techadmin.operation_requests

# This model maps an existing table. It defines exactly the columns listed in
# section E and adds none of its own, so it can be used against a database whose
# schema was created separately. It is deliberately not registered in
# create_tables.py, because the table already exists.

# Security note, from section 7 of the design document. This table stores what
# was asked for, never the credentials involved. request_parameters holds
# sanitized metadata only; a temporary password, an access token or an
# authorization header must never reach this table.
# """

# import uuid
# from datetime import datetime, timezone

# from sqlalchemy import Boolean, DateTime, ForeignKey, Numeric, String, Text, text
# from sqlalchemy.dialects.postgresql import JSONB, UUID
# from sqlalchemy.orm import Mapped, mapped_column

# from App.db.base import Base
# from App.db.connection import DB_SCHEMA


# def utc_now() -> datetime:
#     """Return the current timezone-aware UTC timestamp."""
#     return datetime.now(timezone.utc)


# # Request lifecycle statuses from section E of the design document.
# STATUS_RECEIVED = "RECEIVED"
# STATUS_VALIDATING = "VALIDATING"
# STATUS_AWAITING_APPROVAL = "AWAITING_APPROVAL"
# STATUS_APPROVED = "APPROVED"
# STATUS_REJECTED = "REJECTED"
# STATUS_EXECUTING = "EXECUTING"
# STATUS_SUCCEEDED = "SUCCEEDED"
# STATUS_FAILED = "FAILED"
# STATUS_CANCELLED = "CANCELLED"


# class OperationRequest(Base):
#     """One TechAdmin business request and its lifecycle."""

#     __tablename__ = "operation_requests"
#     __table_args__ = {"schema": DB_SCHEMA}

#     # Primary key and correlation ID, as UUID per section E.
#     #
#     # The application's own request IDs look like "ui_9f29c7fc", which is not a
#     # UUID. operation_audit derives a stable UUID from that string with uuid5,
#     # so the same readable ID always maps to the same row and the log file can
#     # still be tied to this table.
#     request_id: Mapped[uuid.UUID] = mapped_column(
#         UUID(as_uuid=True),
#         primary_key=True,
#         nullable=False,
#     )

#     # The TechAdmin user who submitted the request. Nullable because a request
#     # can arrive before sign-in is enforced on every channel; a null here means
#     # the requester could not be identified, which is itself worth recording.
#     requested_by: Mapped[uuid.UUID | None] = mapped_column(
#         UUID(as_uuid=True),
#         ForeignKey(f"{DB_SCHEMA}.app_users.user_id"),
#         nullable=True,
#         index=True,
#     )

#     # The catalog operation that was identified. Nullable because a request
#     # refused by the guardrails may never resolve to one.
#     operation_id: Mapped[uuid.UUID | None] = mapped_column(
#         UUID(as_uuid=True),
#         ForeignKey(f"{DB_SCHEMA}.operations.operation_id"),
#         nullable=True,
#         index=True,
#     )

#     # WEB, TEAMS, API, PORTAL or another channel.
#     source_channel: Mapped[str] = mapped_column(
#         String(50),
#         nullable=False,
#         default="WEB",
#         server_default=text("'WEB'"),
#     )

#     # The user's original request text, after sanitization.
#     original_request: Mapped[str | None] = mapped_column(Text, nullable=True)

#     # USER, SERVER, GROUP, DEVICE or another resource type.
#     target_type: Mapped[str | None] = mapped_column(String(50), nullable=True)

#     # Masked UPN or resource reference, for dashboards.
#     target_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)

#     # Immutable identifier in the target system, when one is known.
#     target_object_id: Mapped[uuid.UUID | None] = mapped_column(
#         UUID(as_uuid=True),
#         nullable=True,
#     )

#     # Sanitized structured parameters. Never credentials.
#     request_parameters: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

#     # Agent confidence between 0 and 1.
#     intent_confidence: Mapped[float | None] = mapped_column(
#         Numeric(5, 4),
#         nullable=True,
#     )

#     # Current lifecycle status.
#     status: Mapped[str] = mapped_column(
#         String(30),
#         nullable=False,
#         default=STATUS_RECEIVED,
#         server_default=text("'RECEIVED'"),
#         index=True,
#     )

#     requested_at: Mapped[datetime] = mapped_column(
#         DateTime(timezone=True),
#         nullable=False,
#         default=utc_now,
#         server_default=text("CURRENT_TIMESTAMP"),
#     )

#     completed_at: Mapped[datetime | None] = mapped_column(
#         DateTime(timezone=True),
#         nullable=True,
#     )

#     def __repr__(self) -> str:
#         """Concise representation. Carries no credentials."""
#         return (
#             "OperationRequest("
#             f"request_id='{self.request_id}', "
#             f"status='{self.status}', "
#             f"target_reference='{self.target_reference}'"
#             ")"
#         )

"""
SQLAlchemy model for the TechAdmin operation_requests table.
Author: Amit Bhagat

One row per business request submitted to TechAdmin. The request_id is the
end-to-end correlation ID described in section E of the RDBMS Audit and
Operation Tracking design: the same value travels through the application log,
the agent decision, the workflow and the execution record.

The physical PostgreSQL table represented by this model is:

    techadmin.operation_requests

This model maps an existing table. It defines exactly the columns listed in
section E and adds none of its own, so it can be used against a database whose
schema was created separately. It is deliberately not registered in
create_tables.py, because the table already exists.

Security note, from section 7 of the design document. This table stores what
was asked for, never the credentials involved. request_parameters holds
sanitized metadata only; a temporary password, an access token or an
authorization header must never reach this table.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Numeric, String, Text, text
from sqlalchemy import JSON
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from App.db.base import Base
from App.db.connection import DB_SCHEMA


def utc_now() -> datetime:
    """Return the current timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


# Request lifecycle statuses from section E of the design document.
STATUS_RECEIVED = "RECEIVED"
STATUS_VALIDATING = "VALIDATING"
STATUS_AWAITING_APPROVAL = "AWAITING_APPROVAL"
STATUS_APPROVED = "APPROVED"
STATUS_REJECTED = "REJECTED"
STATUS_EXECUTING = "EXECUTING"
STATUS_SUCCEEDED = "SUCCEEDED"
STATUS_FAILED = "FAILED"
STATUS_CANCELLED = "CANCELLED"


class OperationRequest(Base):
    """One TechAdmin business request and its lifecycle."""

    __tablename__ = "operation_requests"
    __table_args__ = {"schema": DB_SCHEMA}

    # Primary key and correlation ID, as UUID per section E.
    #
    # The application's own request IDs look like "ui_9f29c7fc", which is not a
    # UUID. operation_audit derives a stable UUID from that string with uuid5,
    # so the same readable ID always maps to the same row and the log file can
    # still be tied to this table.
    request_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        nullable=False,
    )

    # The TechAdmin user who submitted the request. Nullable because a request
    # can arrive before sign-in is enforced on every channel; a null here means
    # the requester could not be identified, which is itself worth recording.
    requested_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{DB_SCHEMA}.app_users.user_id"),
        nullable=True,
        index=True,
    )

    # The catalog operation that was identified. Nullable because a request
    # refused by the guardrails may never resolve to one.
    operation_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(f"{DB_SCHEMA}.operations.operation_id"),
        nullable=True,
        index=True,
    )

    # WEB, TEAMS, API, PORTAL or another channel.
    source_channel: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="WEB",
        server_default=text("'WEB'"),
    )

    # The user's original request text, after sanitization.
    original_request: Mapped[str | None] = mapped_column(Text, nullable=True)

    # USER, SERVER, GROUP, DEVICE or another resource type.
    target_type: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Masked UPN or resource reference, for dashboards.
    target_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Immutable identifier in the target system, when one is known.
    target_object_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        nullable=True,
    )

    # Sanitized structured parameters. Never credentials.
    #
    # The generic JSON type rather than the PostgreSQL JSONB type, so this
    # model works whether the existing column is JSON, JSONB or TEXT.
    # operation_audit coerces the value to match whatever the column really is.
    request_parameters: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    # Agent confidence between 0 and 1.
    intent_confidence: Mapped[float | None] = mapped_column(
        Numeric(5, 4),
        nullable=True,
    )

    # Current lifecycle status.
    status: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default=STATUS_RECEIVED,
        server_default=text("'RECEIVED'"),
        index=True,
    )

    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        server_default=text("CURRENT_TIMESTAMP"),
    )

    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    def __repr__(self) -> str:
        """Concise representation. Carries no credentials."""
        return (
            "OperationRequest("
            f"request_id='{self.request_id}', "
            f"status='{self.status}', "
            f"target_reference='{self.target_reference}'"
            ")"
        )
