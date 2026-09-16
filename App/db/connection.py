"""
PostgreSQL connection configuration for the TechAdmin application.

This module performs the following tasks:

1. Locates and loads database values from the project .env file.
2. Validates that all required database variables are available.
3. Builds the PostgreSQL connection URL.
4. Creates the shared SQLAlchemy engine.
5. Creates the SQLAlchemy session factory.
6. Provides get_db() for safely opening and closing database sessions.

Security:
- Database credentials are read from environment variables.
- Credentials must never be hardcoded in this file.
- The .env file must not be committed to GitHub.
"""

import os
from pathlib import Path
from urllib.parse import quote_plus

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


# connection.py is located at:
# TechAdmin/App/db/connection.py
#
# parents[2] points to the TechAdmin project directory:
# parents[0] = App/db
# parents[1] = App
# parents[2] = TechAdmin
PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Build the absolute path of the existing project-level .env file.
ENV_FILE = PROJECT_ROOT / ".env"


# Load database configuration from the specified .env file.
#
# override=True means values from this .env file replace matching
# variables already present in the current process environment.
load_dotenv(
    dotenv_path=ENV_FILE,
    override=True,
)


# Read PostgreSQL connection settings from environment variables.
#
# DB_PORT defaults to 5432 when it is not explicitly configured.
# DB_SCHEMA defaults to public when it is not explicitly configured.
DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT", "5432")
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_SCHEMA = os.getenv("DB_SCHEMA", "public")


# Define the variables required before a database connection can
# be created.
required_variables = {
    "DB_HOST": DB_HOST,
    "DB_NAME": DB_NAME,
    "DB_USER": DB_USER,
    "DB_PASSWORD": DB_PASSWORD,
    "DB_SCHEMA": DB_SCHEMA,
}


# Collect the names of variables whose values are missing or empty.
#
# This helps the application fail early with a clear message rather
# than returning a less understandable PostgreSQL connection error.
missing_variables = [
    name
    for name, value in required_variables.items()
    if not value
]


# Stop application startup when required configuration is missing.
#
# The error contains only variable names. It does not expose database
# passwords or other environment values.
if missing_variables:
    raise RuntimeError(
        "Missing database variables: "
        + ", ".join(missing_variables)
    )


# Build the SQLAlchemy PostgreSQL connection URL.
#
# quote_plus() safely encodes special characters in the database
# password before the password becomes part of the connection URL.
#
# Example dialect and driver:
# postgresql+psycopg
DATABASE_URL = (
    f"postgresql+psycopg://{DB_USER}:{quote_plus(DB_PASSWORD)}"
    f"@{DB_HOST}:{DB_PORT}/{DB_NAME}"
)


# Create the shared SQLAlchemy engine.
#
# pool_pre_ping=True:
# Checks a pooled database connection before using it. This helps
# recover when PostgreSQL closed an old or idle connection.
#
# echo=False:
# Prevents SQLAlchemy from printing every SQL statement. Set this
# temporarily to True only when detailed SQL debugging is required.
#
# search_path:
# Makes PostgreSQL look in DB_SCHEMA first and public second when
# an SQL statement uses an unqualified table name.
#
# With DB_SCHEMA=techadmin, the search order is:
# techadmin, public
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    echo=False,
    connect_args={
        "options": f"-csearch_path={DB_SCHEMA},public"
    },
)


# Create the database-session factory.
#
# bind=engine:
# Associates each generated session with the PostgreSQL engine.
#
# autoflush=False:
# Prevents SQLAlchemy from automatically flushing pending changes
# before every query. Application code controls when flushing occurs.
#
# autocommit=False:
# Requires explicit db.commit() for inserts, updates, and deletes.
#
# expire_on_commit=False:
# Keeps loaded model attributes available after db.commit().
SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
)


def get_db():
    """
    Provide one SQLAlchemy database session and close it safely.

    This generator can later be used as a database dependency by
    application routes or services.

    Example:

        def some_service(db=Depends(get_db)):
            ...

    Flow:
    1. Create a database session.
    2. Yield the session to the calling code.
    3. Close the session in the finally block, including when the
       calling code raises an exception.

    The calling code must still use db.commit() for successful data
    changes and db.rollback() when handling failed transactions.
    """

    # Create a new SQLAlchemy session for the current operation.
    db = SessionLocal()

    try:
        # Make the session available to the calling code.
        yield db

    finally:
        # Always return the database connection to the SQLAlchemy
        # connection pool when processing finishes.
        db.close()