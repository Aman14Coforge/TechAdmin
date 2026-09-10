"""
Test the TechAdmin PostgreSQL database connection and schema setup.

This script verifies:

1. Python can connect to PostgreSQL.
2. The connection points to the expected database.
3. The configured PostgreSQL schema exists.
4. The schema is included in the active search path.
5. The connected database user has USAGE permission.
6. The connected database user has CREATE permission.

Run this module from the TechAdmin project directory:

    python -m App.db.test_connection
"""

# text() allows SQL statements to be executed safely through SQLAlchemy.
from sqlalchemy import text

# SQLAlchemyError catches database and SQLAlchemy-related failures.
from sqlalchemy.exc import SQLAlchemyError

# DB_SCHEMA contains the schema configured in the .env file.
# engine is the shared SQLAlchemy database engine.
from App.db.connection import DB_SCHEMA, engine


def test_database_connection() -> None:
    """
    Test the PostgreSQL connection and schema configuration.

    The function opens one database connection, gathers connection
    information, checks the configured schema, validates permissions,
    and prints a final result.

    Raises:
        SQLAlchemyError:
            When PostgreSQL cannot be reached or a database query
            cannot be completed successfully.
    """

    try:
        # Open a connection using the shared SQLAlchemy engine.
        #
        # The connection is automatically returned to the connection
        # pool when the with block finishes.
        with engine.connect() as connection:

            # Retrieve information about the active PostgreSQL
            # connection.
            #
            # current_database():
            # Returns the database selected by DATABASE_URL.
            #
            # current_user:
            # Returns the PostgreSQL role used for the connection.
            #
            # current_schema():
            # Returns the first usable schema in the search path.
            #
            # inet_server_addr():
            # Returns the PostgreSQL server network address.
            #
            # inet_server_port():
            # Returns the PostgreSQL server port.
            #
            # version():
            # Returns the PostgreSQL version and platform details.
            connection_info = connection.execute(
                text(
                    """
                    SELECT
                        current_database() AS database_name,
                        current_user AS database_user,
                        current_schema() AS current_schema,
                        inet_server_addr()::text AS server_address,
                        inet_server_port() AS server_port,
                        version() AS postgres_version
                    """
                )
            ).mappings().one()

            # Read the schema search path applied to the connection.
            #
            # With the current TechAdmin configuration, this should
            # normally show:
            #
            # techadmin,public
            search_path = connection.execute(
                text("SHOW search_path")
            ).scalar_one()

            # Return the schemas that PostgreSQL can currently use
            # from the configured search path.
            #
            # Schemas that do not exist or cannot be accessed are not
            # included in this result.
            effective_schemas = connection.execute(
                text("SELECT current_schemas(false)")
            ).scalar_one()

            # Check whether DB_SCHEMA physically exists in the active
            # PostgreSQL database.
            #
            # A PostgreSQL schema exists only inside the database in
            # which the schema was created.
            schema_exists = connection.execute(
                text(
                    """
                    SELECT EXISTS (
                        SELECT 1
                        FROM pg_namespace
                        WHERE nspname = :schema_name
                    )
                    """
                ),
                {
                    "schema_name": DB_SCHEMA,
                },
            ).scalar_one()

            # Print basic connection and schema information.
            print()
            print("Database connection successful")
            print("=" * 60)

            print(
                f"Database: "
                f"{connection_info['database_name']}"
            )

            print(
                f"Database user: "
                f"{connection_info['database_user']}"
            )

            print(
                f"Server address: "
                f"{connection_info['server_address']}"
            )

            print(
                f"Server port: "
                f"{connection_info['server_port']}"
            )

            print(f"Configured schema: {DB_SCHEMA}")

            print(
                f"Current schema: "
                f"{connection_info['current_schema']}"
            )

            print(f"Search path: {search_path}")

            print(
                f"Effective schemas: "
                f"{effective_schemas}"
            )

            print(
                f"Configured schema exists: "
                f"{schema_exists}"
            )

            # Stop the remaining schema checks when the configured
            # schema does not exist.
            #
            # Permission functions should not be called for a missing
            # schema because PostgreSQL will raise InvalidSchemaName.
            if not schema_exists:
                print()

                print(
                    f"RESULT: Schema '{DB_SCHEMA}' does not exist "
                    f"in database "
                    f"'{connection_info['database_name']}'."
                )

                print(
                    f"Create it inside "
                    f"'{connection_info['database_name']}', "
                    f"not in another database."
                )

                return

            # Check the connected PostgreSQL user's privileges on the
            # configured schema.
            #
            # USAGE:
            # Allows the user to access objects inside the schema,
            # subject to permissions on those individual objects.
            #
            # CREATE:
            # Allows the user to create objects such as tables inside
            # the schema.
            permissions = connection.execute(
                text(
                    """
                    SELECT
                        has_schema_privilege(
                            current_user,
                            :schema_name,
                            'USAGE'
                        ) AS has_usage,
                        has_schema_privilege(
                            current_user,
                            :schema_name,
                            'CREATE'
                        ) AS has_create
                    """
                ),
                {
                    "schema_name": DB_SCHEMA,
                },
            ).mappings().one()

            # Display schema permission results.
            print(
                f"Schema USAGE permission: "
                f"{permissions['has_usage']}"
            )

            print(
                f"Schema CREATE permission: "
                f"{permissions['has_create']}"
            )

            print("=" * 60)

            # Perform the final configuration checks in sequence.
            #
            # This verifies the expected TechAdmin database name,
            # required schema permissions, and effective schema.
            if connection_info["database_name"] != "techadmin_dev":
                print(
                    "RESULT: Connected to the wrong database."
                )

            elif not permissions["has_usage"]:
                print(
                    f"RESULT: User cannot use schema "
                    f"'{DB_SCHEMA}'."
                )

            elif not permissions["has_create"]:
                print(
                    f"RESULT: User cannot create tables in "
                    f"'{DB_SCHEMA}'."
                )

            elif (
                connection_info["current_schema"]
                != DB_SCHEMA
            ):
                print(
                    f"RESULT: Schema '{DB_SCHEMA}' exists, "
                    f"but it is not first in the effective "
                    f"search path."
                )

            else:
                print(
                    f"RESULT: Database connection and schema "
                    f"configuration are correct."
                )

    except SQLAlchemyError as error:
        # Display database or SQLAlchemy failures.
        #
        # The original exception is raised again so that command-line
        # execution, tests, or calling applications receive a failure
        # status instead of silently continuing.
        print()
        print("Database connection failed")
        print(f"Error type: {type(error).__name__}")
        print(f"Error: {error}")

        raise


# Run the connection test only when this file is executed directly
# as a Python module.
#
# This block does not run when another Python file imports this
# module.
if __name__ == "__main__":
    test_database_connection()