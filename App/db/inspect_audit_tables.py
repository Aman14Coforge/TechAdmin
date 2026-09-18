"""
Inspect the live audit tables and compare them to the models.
Author: Amit Bhagat

Run from the project root:

    python -m App.db.inspect_audit_tables

Prints the columns PostgreSQL actually has for operations and
operation_requests, and flags anything the SQLAlchemy models expect that the
database does not provide, or the other way round.

A mismatch is the usual cause of AUDIT_REQUEST_CLOSE_FAILED with a
ProgrammingError: the model writes a column the table does not have.
"""

from sqlalchemy import inspect

from App.db.connection import DB_SCHEMA, engine
from App.db.models.operation_executions import OperationExecution
from App.db.models.operation_requests import OperationRequest
from App.db.models.operations import Operation

MODELS = (Operation, OperationRequest, OperationExecution)


def describe(table_name: str) -> dict:
    """
    Read the live columns of one table.

    Args:
        table_name: The table to inspect, without the schema prefix.

    Returns:
        Mapping of column name to its database type, empty when the table does
        not exist.
    """
    inspector = inspect(engine)

    if not inspector.has_table(table_name, schema=DB_SCHEMA):
        return {}

    return {
        column["name"]: str(column["type"])
        for column in inspector.get_columns(table_name, schema=DB_SCHEMA)
    }


def main() -> None:
    """Print each table's live columns and compare them to the model."""
    print(f"schema: {DB_SCHEMA}\n")

    for model in MODELS:
        table_name = model.__tablename__
        live = describe(table_name)

        print("=" * 70)
        print(f"{DB_SCHEMA}.{table_name}")
        print("=" * 70)

        if not live:
            print("  TABLE NOT FOUND in this schema.")
            print("  Check DB_SCHEMA in .env, or create the table.\n")
            continue

        expected = {column.name for column in model.__table__.columns}

        print("  live columns:")
        for name, column_type in live.items():
            marker = " " if name in expected else "  <- not in model"
            print(f"    {name:24} {column_type:28}{marker}")

        missing = expected - set(live)

        if missing:
            print("\n  MISSING FROM THE DATABASE, written by the model:")
            for name in sorted(missing):
                print(f"    {name}")
            print("\n  These are what cause AUDIT_REQUEST_CLOSE_FAILED.")
        else:
            print("\n  Every column the model writes exists in the table.")

        print()


if __name__ == "__main__":
    main()
