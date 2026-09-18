"""
Create and validate TechAdmin database tables.

Current managed tables:
1. techadmin.app_users
2. techadmin.operations

This module manages table structure only.

It does not:
- Insert users
- Insert operations
- Update business data
- Delete database records

Data insertion is handled separately by:
- App/db/seed_app_user.py
- App/db/seed_operations.py

Important:
checkfirst=True creates a missing table but does not modify the
structure of an existing table. Future schema changes should be
managed using Alembic migrations.
"""

from sqlalchemy import inspect, text
from sqlalchemy.exc import SQLAlchemyError

from App.db.connection import DB_SCHEMA, engine
from App.db.models.app_users import AppUser
from App.db.models.operations import Operation


# Exact expected column set for techadmin.app_users.
APP_USERS_EXPECTED_COLUMNS = {
    "user_id",
    "entra_object_id",
    "user_principal_name",
    "display_name",
    "department",
    "is_active",
    "created_at",
    "updated_at",
}


# Exact expected column set for techadmin.operations.
OPERATIONS_EXPECTED_COLUMNS = {
    "operation_id",
    "operation_code",
    "operation_name",
    "execution_type",
    "tool_name",
    "script_name",
    "risk_level",
    "requires_approval",
    "is_active",
    "created_at",
}


def verify_schema_exists() -> None:
    """
    Confirm that DB_SCHEMA exists in the configured database.

    For the current TechAdmin configuration, DB_SCHEMA should be:
    techadmin
    """

    with engine.connect() as connection:
        schema_exists = connection.execute(
            text(
                """
                SELECT EXISTS (
                    SELECT 1
                    FROM information_schema.schemata
                    WHERE schema_name = :schema_name
                )
                """
            ),
            {
                "schema_name": DB_SCHEMA,
            },
        ).scalar_one()

    if not schema_exists:
        raise RuntimeError(
            f"Schema '{DB_SCHEMA}' does not exist in the "
            "configured PostgreSQL database."
        )


def create_tables() -> None:
    """
    Create all currently registered TechAdmin tables.

    Each model table is created only when it does not already exist.
    Existing app_users records, including the five seeded users, are
    not deleted or modified.
    """

    with engine.begin() as connection:
        AppUser.__table__.create(
            bind=connection,
            checkfirst=True,
        )

        Operation.__table__.create(
            bind=connection,
            checkfirst=True,
        )


def validate_table(
    *,
    table_name: str,
    expected_columns: set[str],
) -> None:
    """
    Validate one table against its expected column set.

    Args:
        table_name:
            Name of the physical PostgreSQL table.

        expected_columns:
            Exact set of column names expected by the application.

    Raises:
        RuntimeError:
            If the table does not exist or its column structure
            differs from the SQLAlchemy implementation.
    """

    inspector = inspect(engine)

    table_exists = inspector.has_table(
        table_name=table_name,
        schema=DB_SCHEMA,
    )

    if not table_exists:
        raise RuntimeError(
            f"Table '{DB_SCHEMA}.{table_name}' was not created."
        )

    columns = inspector.get_columns(
        table_name=table_name,
        schema=DB_SCHEMA,
    )

    actual_columns = {
        column["name"]
        for column in columns
    }

    extra_columns = actual_columns - expected_columns
    missing_columns = expected_columns - actual_columns

    if extra_columns or missing_columns:
        raise RuntimeError(
            f"Table '{DB_SCHEMA}.{table_name}' does not match "
            "the expected model. "
            f"Extra columns: {sorted(extra_columns)}. "
            f"Missing columns: {sorted(missing_columns)}."
        )

    print()
    print("=" * 70)
    print(f"Table: {DB_SCHEMA}.{table_name}")
    print("Status: Available")
    print("Structure: Valid")
    print()
    print("Columns:")

    for column in columns:
        print(
            f"- {column['name']}: "
            f"{column['type']}, "
            f"nullable={column['nullable']}"
        )

    print("=" * 70)


def setup_database() -> None:
    """
    Run the TechAdmin table setup process.

    Execution sequence:
    1. Verify that the configured schema exists.
    2. Create missing tables.
    3. Validate app_users.
    4. Validate operations.
    """

    try:
        verify_schema_exists()
        create_tables()

        validate_table(
            table_name="app_users",
            expected_columns=APP_USERS_EXPECTED_COLUMNS,
        )

        validate_table(
            table_name="operations",
            expected_columns=OPERATIONS_EXPECTED_COLUMNS,
        )

        print()
        print("Database table setup completed successfully.")

    except (SQLAlchemyError, RuntimeError) as error:
        print()
        print("Database table setup failed.")
        print(f"Error type: {type(error).__name__}")
        print(f"Error: {error}")

        raise


if __name__ == "__main__":
    setup_database()