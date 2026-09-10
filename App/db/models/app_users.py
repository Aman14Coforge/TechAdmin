"""
SQLAlchemy model for the TechAdmin app_users table.

This model defines:

1. The PostgreSQL schema and table name.
2. The columns available in app_users.
3. The PostgreSQL data type of each column.
4. Primary-key and uniqueness constraints.
5. Automatic generation of user_id.
6. Automatic generation of created_at and updated_at.
7. Automatic update behavior for updated_at.

The physical PostgreSQL table represented by this model is:

    techadmin.app_users

The actual schema name is read from DB_SCHEMA in the project .env
file, so another environment can use a different schema if required.
"""

# uuid is used to generate and represent UUID values in Python.
import uuid

# datetime is used for timestamp values.
# timezone is used to generate timezone-aware UTC timestamps.
from datetime import datetime, timezone

# SQLAlchemy column types:
#
# Boolean:
# Maps Python True/False values to PostgreSQL BOOLEAN.
#
# DateTime:
# Maps Python datetime values to PostgreSQL timestamp columns.
#
# String:
# Maps Python strings to PostgreSQL VARCHAR columns.
#
# text:
# Defines SQL expressions used as PostgreSQL server defaults.
from sqlalchemy import Boolean, DateTime, String, text

# PostgreSQL-specific UUID type.
#
# as_uuid=True means SQLAlchemy returns Python uuid.UUID objects
# instead of ordinary strings.
from sqlalchemy.dialects.postgresql import UUID

# Mapped:
# Provides SQLAlchemy 2.x type annotations for model attributes.
#
# mapped_column:
# Defines each database column in a SQLAlchemy 2.x model.
from sqlalchemy.orm import Mapped, mapped_column

# Base is the common declarative base inherited by all TechAdmin
# SQLAlchemy models.
from App.db.base import Base

# DB_SCHEMA is loaded from the root .env file by connection.py.
#
# For the current configuration:
#
#     DB_SCHEMA=techadmin
#
# Therefore, this model maps to techadmin.app_users.
from App.db.connection import DB_SCHEMA


def utc_now() -> datetime:
    """
    Return the current timezone-aware UTC date and time.

    This function is used as the Python-side default for created_at
    and updated_at.

    A function reference is supplied to SQLAlchemy instead of calling
    the function while the model is imported. This ensures a new
    timestamp is generated whenever a record is added or updated.
    """

    return datetime.now(timezone.utc)


class AppUser(Base):
    """
    SQLAlchemy model representing one TechAdmin application user.

    Each AppUser object represents one row in the PostgreSQL
    app_users table.

    The model contains only the fields currently defined for the
    TechAdmin app_users table:

    - user_id
    - entra_object_id
    - user_principal_name
    - display_name
    - department
    - is_active
    - created_at
    - updated_at
    """

    # Name of the physical PostgreSQL table.
    __tablename__ = "app_users"

    # Explicitly place the table inside the schema configured through
    # DB_SCHEMA.
    #
    # This prevents SQLAlchemy from accidentally creating the table
    # under the default public schema.
    __table_args__ = {
        "schema": DB_SCHEMA,
    }

    # Internal immutable primary key for a TechAdmin user.
    #
    # UUID(as_uuid=True):
    # Stores the value as PostgreSQL UUID and uses uuid.UUID in Python.
    #
    # primary_key=True:
    # Uniquely identifies every app_users table row.
    #
    # default=uuid.uuid4:
    # Generates the UUID through Python when SQLAlchemy adds a user.
    #
    # server_default=text("gen_random_uuid()"):
    # Allows PostgreSQL to generate a UUID when a row is inserted
    # directly through SQL rather than through the Python application.
    #
    # nullable=False:
    # Prevents a user row from existing without a user_id.
    #
    # This value should never be changed after user creation.
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
        nullable=False,
    )

    # Stable external identity identifier from Microsoft Entra ID.
    #
    # unique=True:
    # Prevents the same Entra Object ID from being assigned to
    # multiple TechAdmin users.
    #
    # nullable=False:
    # Requires an Entra Object ID for every current user record.
    #
    # index=True:
    # Creates an index to support faster identity lookup using the
    # Entra Object ID.
    entra_object_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        unique=True,
        nullable=False,
        index=True,
    )

    # Organizational User Principal Name, commonly called the UPN.
    #
    # Example:
    #
    #     aman.3.mishra@coforge.com
    #
    # unique=True:
    # Prevents two records from storing the same normalized UPN.
    #
    # nullable=False:
    # Requires every TechAdmin user to have a UPN.
    #
    # index=True:
    # Supports faster user searches using the UPN.
    user_principal_name: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
        index=True,
    )

    # Friendly name displayed in TechAdmin screens, logs, and reports.
    #
    # This value is required and supports up to 255 characters.
    display_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
    )

    # User's department or organizational unit.
    #
    # nullable=True:
    # Allows the department to be omitted when it is not available.
    #
    # The column supports up to 150 characters.
    department: Mapped[str | None] = mapped_column(
        String(150),
        nullable=True,
    )

    # Local TechAdmin access-status flag.
    #
    # True:
    # The user is active and may be considered for TechAdmin access.
    #
    # False:
    # The user is inactive and should be rejected by later
    # authorization logic.
    #
    # default=True:
    # Python uses True when SQLAlchemy creates a user without an
    # explicitly supplied is_active value.
    #
    # server_default=text("true"):
    # PostgreSQL uses TRUE when a row is inserted directly through SQL
    # without an explicitly supplied is_active value.
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("true"),
    )

    # Timestamp showing when the user row was first created.
    #
    # DateTime(timezone=True):
    # Maps to a timezone-aware PostgreSQL timestamp.
    #
    # default=utc_now:
    # Python generates the current UTC timestamp during creation.
    #
    # server_default=text("CURRENT_TIMESTAMP"):
    # PostgreSQL generates the current timestamp when a row is inserted
    # directly through SQL.
    #
    # created_at should never be changed when an existing user is
    # updated.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        server_default=text("CURRENT_TIMESTAMP"),
    )

    # Timestamp showing when the user row was last changed.
    #
    # default=utc_now:
    # Generates the timestamp when a new user is created.
    #
    # onupdate=utc_now:
    # Generates a new timestamp when SQLAlchemy updates the model.
    #
    # server_default=text("CURRENT_TIMESTAMP"):
    # Generates the timestamp for direct SQL INSERT operations.
    #
    # Important:
    # onupdate works for updates performed through SQLAlchemy. Direct
    # SQL UPDATE statements must explicitly update this column unless
    # a PostgreSQL trigger is added later.
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=utc_now,
        onupdate=utc_now,
        server_default=text("CURRENT_TIMESTAMP"),
    )

    def __repr__(self) -> str:
        """
        Return a concise developer-friendly representation.

        This method is useful in debugging, logs, and the Python
        console.

        The representation intentionally includes identity and status
        fields but does not include credentials or authentication
        secrets.
        """

        return (
            "AppUser("
            f"user_id={self.user_id}, "
            f"entra_object_id={self.entra_object_id}, "
            f"user_principal_name='{self.user_principal_name}', "
            f"is_active={self.is_active}"
            ")"
        )