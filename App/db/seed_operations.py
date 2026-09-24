"""
Insert or update approved TechAdmin operations.

The operations table is a controlled catalog of tools that the
TechAdmin workflow can use.

Current operations:
1. GET_USER_DETAILS
2. RESET_PASSWORD
3. UNLOCK_USER
4. FAILED_LOGIN_INVESTIGATION
5. ADD_USER_TO_GROUP
6. REMOVE_USER_FROM_GROUP

System-generated fields:
- operation_id
- created_at

Existing operation_id and created_at values are preserved when an
operation is updated.
"""

from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from App.db.connection import SessionLocal
from App.db.models.operations import Operation


# Approved operation configuration.
#
# operation_id and created_at are not supplied here because the
# Operation model generates them automatically.
#
# script_name is None for API operations because no script is used.
APPROVED_OPERATIONS: list[dict[str, Any]] = [
    {
        "operation_code": "GET_USER_DETAILS",
        "operation_name": "Get User Details",
        "execution_type": "API",
        "tool_name": "GET_USER_DETAILS",
        "script_name": None,
        "risk_level": "LOW",
        "requires_approval": False,
        "is_active": True,
    },
    {
        "operation_code": "RESET_PASSWORD",
        "operation_name": "Reset Password",
        "execution_type": "API",
        "tool_name": "RESET_PASSWORD",
        "script_name": None,
        "risk_level": "HIGH",
        "requires_approval": True,
        "is_active": True,
    },
    {
        "operation_code": "UNLOCK_USER",
        "operation_name": "Unlock User",
        "execution_type": "SCRIPT",
        "tool_name": "UNLOCK_ACCOUNT",
        "script_name": "Invoke-UnlockUser.ps1",
        "risk_level": "MEDIUM",
        "requires_approval": False,
        "is_active": True,
    },
    {
        "operation_code": "FAILED_LOGIN_INVESTIGATION",
        "operation_name": "Lockout / Failed Login Investigation",
        "execution_type": "API",
        "tool_name": "INVESTIGATE_FAILED_LOGIN",
        "script_name": None,
        "risk_level": "LOW",
        "requires_approval": False,
        "is_active": True,
    },
    {
        "operation_code": "ADD_USER_TO_GROUP",
        "operation_name": "Add User To Group",
        "execution_type": "SCRIPT",
        "tool_name": "MANAGE_ACCESS",
        "script_name": "Invoke-AddUserToGroup.ps1",
        "risk_level": "HIGH",
        "requires_approval": False,
        "is_active": True,
    },
    {
        "operation_code": "REMOVE_USER_FROM_GROUP",
        "operation_name": "Remove User From Group",
        "execution_type": "SCRIPT",
        "tool_name": "MANAGE_ACCESS",
        "script_name": "Invoke-RemoveUserFromGroup.ps1",
        "risk_level": "HIGH",
        "requires_approval": True,
        "is_active": True,
    },
]


# Values currently supported by the TechAdmin database design.
ALLOWED_EXECUTION_TYPES = {"API", "SCRIPT", "JOB"}

ALLOWED_RISK_LEVELS = {
    "LOW",
    "MEDIUM",
    "HIGH",
    "CRITICAL",
}


def normalize_operation_data(
    operation_data: dict[str, Any],
) -> dict[str, Any]:
    """
    Clean and normalize operation data before storing it.

    Machine-readable values are converted to uppercase.
    Blank script names are converted to None, which PostgreSQL
    stores as NULL.
    """

    script_name = operation_data.get("script_name")

    return {
        "operation_code": (
            operation_data["operation_code"].strip().upper()
        ),
        "operation_name": (
            operation_data["operation_name"].strip()
        ),
        "execution_type": (
            operation_data["execution_type"].strip().upper()
        ),
        "tool_name": operation_data["tool_name"].strip(),
        "script_name": (
            script_name.strip() if script_name else None
        ),
        "risk_level": (
            operation_data["risk_level"].strip().upper()
        ),
        "requires_approval": bool(
            operation_data["requires_approval"]
        ),
        "is_active": bool(operation_data["is_active"]),
    }


def validate_operation_data(
    operation_data: dict[str, Any],
) -> None:
    """
    Validate configuration before inserting or updating a row.
    """

    execution_type = operation_data["execution_type"]
    risk_level = operation_data["risk_level"]
    script_name = operation_data["script_name"]

    if execution_type not in ALLOWED_EXECUTION_TYPES:
        raise ValueError(
            f"Invalid execution_type: {execution_type}. "
            f"Allowed values: {sorted(ALLOWED_EXECUTION_TYPES)}"
        )

    if risk_level not in ALLOWED_RISK_LEVELS:
        raise ValueError(
            f"Invalid risk_level: {risk_level}. "
            f"Allowed values: {sorted(ALLOWED_RISK_LEVELS)}"
        )

    # Script-based operations must identify the approved script.
    if execution_type == "SCRIPT" and not script_name:
        raise ValueError(
            "script_name is required for a SCRIPT operation."
        )

    # API operations do not execute script files.
    if execution_type == "API" and script_name is not None:
        raise ValueError(
            "script_name must be empty for an API operation."
        )


def find_operation(
    db: Session,
    operation_code: str,
) -> Operation | None:
    """
    Find an operation by its unique operation code.
    """

    return db.scalar(
        select(Operation).where(
            Operation.operation_code == operation_code
        )
    )


def operation_has_changed(
    existing: Operation,
    new_data: dict[str, Any],
) -> bool:
    """
    Return True if any editable operation property changed.

    operation_id and created_at are not compared because they
    must remain unchanged after initial creation.
    """

    return any(
        (
            existing.operation_name
            != new_data["operation_name"],
            existing.execution_type
            != new_data["execution_type"],
            existing.tool_name
            != new_data["tool_name"],
            existing.script_name
            != new_data["script_name"],
            existing.risk_level
            != new_data["risk_level"],
            existing.requires_approval
            != new_data["requires_approval"],
            existing.is_active
            != new_data["is_active"],
        )
    )


def create_operation(
    db: Session,
    operation_data: dict[str, Any],
) -> Operation:
    """
    Create one new operation.

    The Operation model automatically generates operation_id and
    created_at.
    """

    operation = Operation(
        operation_code=operation_data["operation_code"],
        operation_name=operation_data["operation_name"],
        execution_type=operation_data["execution_type"],
        tool_name=operation_data["tool_name"],
        script_name=operation_data["script_name"],
        risk_level=operation_data["risk_level"],
        requires_approval=operation_data[
            "requires_approval"
        ],
        is_active=operation_data["is_active"],
    )

    db.add(operation)
    db.flush()

    return operation


def update_operation(
    db: Session,
    existing: Operation,
    operation_data: dict[str, Any],
) -> Operation:
    """
    Update an existing operation's editable fields.

    operation_id, operation_code, and created_at are preserved.
    """

    existing.operation_name = operation_data[
        "operation_name"
    ]
    existing.execution_type = operation_data[
        "execution_type"
    ]
    existing.tool_name = operation_data["tool_name"]
    existing.script_name = operation_data["script_name"]
    existing.risk_level = operation_data["risk_level"]
    existing.requires_approval = operation_data[
        "requires_approval"
    ]
    existing.is_active = operation_data["is_active"]

    db.flush()

    return existing


def process_operation(
    db: Session,
    operation_data: dict[str, Any],
) -> tuple[Operation, str]:
    """
    Create, update, or skip one operation.

    Returns the final Operation object and one of:
    CREATED, UPDATED, or UNCHANGED.
    """

    normalized_data = normalize_operation_data(
        operation_data
    )

    validate_operation_data(normalized_data)

    existing = find_operation(
        db,
        normalized_data["operation_code"],
    )

    if existing is None:
        operation = create_operation(
            db,
            normalized_data,
        )
        return operation, "CREATED"

    if not operation_has_changed(
        existing,
        normalized_data,
    ):
        return existing, "UNCHANGED"

    operation = update_operation(
        db,
        existing,
        normalized_data,
    )

    return operation, "UPDATED"


def print_operation(
    operation: Operation,
    action: str,
) -> None:
    """
    Display the final stored operation values.
    """

    script_name = operation.script_name or "NULL"

    print()
    print("-" * 70)
    print(f"Action:             {action}")
    print(f"Operation ID:       {operation.operation_id}")
    print(f"Operation Code:     {operation.operation_code}")
    print(f"Operation Name:     {operation.operation_name}")
    print(f"Execution Type:     {operation.execution_type}")
    print(f"Tool Name:          {operation.tool_name}")
    print(f"Script Name:        {script_name}")
    print(f"Risk Level:         {operation.risk_level}")
    print(f"Requires Approval:  {operation.requires_approval}")
    print(f"Active:             {operation.is_active}")
    print(f"Created At:         {operation.created_at}")


def seed_operations() -> None:
    """
    Insert or update all approved operations in one transaction.

    If any operation fails, all uncommitted changes are rolled back.
    """

    with SessionLocal() as db:
        try:
            results: list[tuple[Operation, str]] = []

            for operation_data in APPROVED_OPERATIONS:
                operation, action = process_operation(
                    db,
                    operation_data,
                )

                results.append((operation, action))

            # Save all successful changes.
            db.commit()

            created = 0
            updated = 0
            unchanged = 0

            for operation, action in results:
                # Reload final database-generated values.
                db.refresh(operation)

                print_operation(operation, action)

                if action == "CREATED":
                    created += 1
                elif action == "UPDATED":
                    updated += 1
                else:
                    unchanged += 1

            print()
            print("=" * 70)
            print("Operation seed completed successfully")
            print(f"Created:   {created}")
            print(f"Updated:   {updated}")
            print(f"Unchanged: {unchanged}")
            print("=" * 70)

        except (
            IntegrityError,
            SQLAlchemyError,
            ValueError,
        ) as error:
            # Discard all uncommitted changes if anything fails.
            db.rollback()

            print()
            print("Operation seed failed")
            print(f"Error type: {type(error).__name__}")
            print(f"Error: {error}")

            raise


if __name__ == "__main__":
    seed_operations()