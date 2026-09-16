"""
Interactively add users to the TechAdmin app_users table.

The operator running this module must enter:

1. Microsoft Entra Object ID
2. User Principal Name
3. Display Name
4. Department

Python automatically generates:

- user_id
- created_at
- updated_at

The script also automatically sets:

- is_active = True

Existing users are protected from duplication. The script checks both
the Microsoft Entra Object ID and User Principal Name before inserting
a new database record.
"""

import re
import uuid

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from App.db.connection import SessionLocal
from App.db.models.app_users import AppUser


def read_required_input(prompt: str) -> str:
    """
    Read a required value from the terminal.

    Empty or whitespace-only values are rejected. The user continues
    to receive the prompt until a valid non-empty value is entered.
    """

    while True:
        value = input(prompt).strip()

        if value:
            return value

        print("This value is required. Please enter a value.")


def read_entra_object_id() -> uuid.UUID:
    """
    Read and validate a Microsoft Entra Object ID.

    Entra Object IDs are stored in PostgreSQL using the UUID data type.
    The entered value must therefore be a valid UUID.
    """

    while True:
        entered_value = read_required_input(
            "Enter Entra Object ID: "
        )

        try:
            return uuid.UUID(entered_value)

        except ValueError:
            print()
            print("Invalid Entra Object ID.")
            print(
                "Please enter a valid UUID, for example:"
            )
            print(
                "12345678-1234-1234-1234-123456789abc"
            )
            print()


def read_user_principal_name() -> str:
    """
    Read and perform basic validation on the User Principal Name.

    The UPN is normalized to lowercase before being stored. This
    prevents differences such as User@Coforge.com and
    user@coforge.com from producing inconsistent records.

    This validation checks only the expected basic UPN structure.
    Microsoft Entra remains the authoritative source for identities.
    """

    basic_upn_pattern = re.compile(
        r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
    )

    while True:
        entered_upn = read_required_input(
            "Enter User Principal Name: "
        ).lower()

        if basic_upn_pattern.fullmatch(entered_upn):
            return entered_upn

        print()
        print("Invalid User Principal Name format.")
        print(
            "Example: employee.name@coforge.com"
        )
        print()


def read_display_name() -> str:
    """
    Read the display name shown for the TechAdmin user.
    """

    return read_required_input(
        "Enter Display Name: "
    )


def read_department() -> str:
    """
    Read the user's department.

    Although department is nullable in the database design, it is
    required by this interactive input process as requested.
    """

    return read_required_input(
        "Enter Department: "
    )


def find_user_by_entra_object_id(
    db: Session,
    entra_object_id: uuid.UUID,
) -> AppUser | None:
    """
    Search for an existing user by Microsoft Entra Object ID.

    The Entra Object ID must be unique in app_users.
    """

    return db.scalar(
        select(AppUser).where(
            AppUser.entra_object_id == entra_object_id
        )
    )


def find_user_by_upn(
    db: Session,
    user_principal_name: str,
) -> AppUser | None:
    """
    Search for an existing user by UPN.

    A case-insensitive comparison is used so that different letter
    casing does not create duplicate users.
    """

    return db.scalar(
        select(AppUser).where(
            func.lower(AppUser.user_principal_name)
            == user_principal_name.lower()
        )
    )


def print_user_details(
    user: AppUser,
    heading: str,
) -> None:
    """
    Print all stored app_users values for one user.

    This output provides visible confirmation of the values generated
    by Python and the values stored in PostgreSQL.
    """

    print()
    print("=" * 70)
    print(heading)
    print("=" * 70)
    print(f"User ID:             {user.user_id}")
    print(f"Entra Object ID:     {user.entra_object_id}")
    print(f"User Principal Name: {user.user_principal_name}")
    print(f"Display Name:        {user.display_name}")
    print(f"Department:          {user.department}")
    print(f"Active:              {user.is_active}")
    print(f"Created At:          {user.created_at}")
    print(f"Updated At:          {user.updated_at}")
    print("=" * 70)


def collect_user_input() -> dict:
    """
    Collect all required user values from the terminal.

    user_id, is_active, created_at, and updated_at are deliberately
    not requested because those values are controlled by Python.
    """

    print()
    print("=" * 70)
    print("Add a New TechAdmin User")
    print("=" * 70)
    print(
        "Enter the following Microsoft Entra user information."
    )
    print()

    return {
        "entra_object_id": read_entra_object_id(),
        "user_principal_name": (
            read_user_principal_name()
        ),
        "display_name": read_display_name(),
        "department": read_department(),
    }


def create_app_user(
    db: Session,
    user_data: dict,
) -> AppUser:
    """
    Create and persist one new TechAdmin user.

    The AppUser SQLAlchemy model automatically generates:

    - user_id using uuid.uuid4()
    - created_at using the current UTC timestamp
    - updated_at using the current UTC timestamp

    is_active is set to True because an interactively added user is
    being registered as an active TechAdmin user.
    """

    app_user = AppUser(
        entra_object_id=user_data["entra_object_id"],
        user_principal_name=(
            user_data["user_principal_name"]
        ),
        display_name=user_data["display_name"],
        department=user_data["department"],
        is_active=True,
    )

    db.add(app_user)
    db.commit()

    # Refresh the SQLAlchemy object to load the final values stored
    # by PostgreSQL, including generated identifiers and timestamps.
    db.refresh(app_user)

    return app_user


def add_user_interactively() -> bool:
    """
    Collect input, validate uniqueness, and insert a new user.

    Returns:
        True when a new user is inserted.
        False when insertion is skipped because the user exists.
    """

    user_data = collect_user_input()

    with SessionLocal() as db:
        try:
            # First check the stable Entra Object ID.
            existing_oid_user = find_user_by_entra_object_id(
                db=db,
                entra_object_id=(
                    user_data["entra_object_id"]
                ),
            )

            if existing_oid_user is not None:
                print()
                print(
                    "A user with this Entra Object ID "
                    "already exists."
                )

                print_user_details(
                    user=existing_oid_user,
                    heading="Existing User",
                )

                print("No duplicate user was inserted.")

                return False

            # Check the UPN separately. This prevents a new Entra
            # Object ID from being assigned to an existing UPN.
            existing_upn_user = find_user_by_upn(
                db=db,
                user_principal_name=(
                    user_data["user_principal_name"]
                ),
            )

            if existing_upn_user is not None:
                print()
                print(
                    "A user with this User Principal Name "
                    "already exists."
                )

                print_user_details(
                    user=existing_upn_user,
                    heading="Existing User",
                )

                print("No duplicate user was inserted.")

                return False

            app_user = create_app_user(
                db=db,
                user_data=user_data,
            )

            print_user_details(
                user=app_user,
                heading=(
                    "TechAdmin User Created Successfully"
                ),
            )

            return True

        except IntegrityError as error:
            # IntegrityError is raised when a database uniqueness
            # rule or another database constraint is violated.
            db.rollback()

            print()
            print("Could not insert the user.")
            print(
                "The Entra Object ID or User Principal Name "
                "may already exist."
            )
            print(
                f"Database error: {error.orig}"
            )

            return False

        except SQLAlchemyError as error:
            # Undo any uncommitted database changes when a database
            # or connection error occurs.
            db.rollback()

            print()
            print("Could not insert the user.")
            print(f"Error type: {type(error).__name__}")
            print(f"Error: {error}")

            return False


def ask_to_add_another_user() -> bool:
    """
    Ask whether the operator wants to add another user.

    Only Y and N are accepted to avoid accidental behavior.
    """

    while True:
        answer = input(
            "\nDo you want to add another user? (Y/N): "
        ).strip().lower()

        if answer in {"y", "yes"}:
            return True

        if answer in {"n", "no"}:
            return False

        print("Please enter Y for Yes or N for No.")


def seed_app_users() -> None:
    """
    Run the interactive user creation process.

    The operator can add multiple users in one execution. Every user
    is committed independently, so a duplicate or invalid user does
    not remove users successfully created earlier in the same run.
    """

    while True:
        add_user_interactively()

        if not ask_to_add_another_user():
            print()
            print("User creation process completed.")
            break


if __name__ == "__main__":
    seed_app_users()