"""
Shared SQLAlchemy declarative base for TechAdmin database models.

Every SQLAlchemy ORM model in the TechAdmin project should inherit
from the Base class defined in this file.

Current examples:

    class AppUser(Base):
        ...

    class Operation(Base):
        ...

Using one shared Base allows SQLAlchemy to maintain a common metadata
collection containing all registered table definitions.
"""

# DeclarativeBase is SQLAlchemy's base class for defining ORM models
# using the SQLAlchemy 2.x declarative mapping style.
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """
    Common parent class for all TechAdmin SQLAlchemy ORM models.

    This class currently does not require custom methods or fields.
    Inheriting from DeclarativeBase provides SQLAlchemy functionality
    such as:

    - Model-to-table mapping
    - Shared table metadata
    - Column registration
    - Primary-key mapping
    - Relationship mapping
    - Table creation support

    Models such as AppUser and Operation inherit from this class so
    SQLAlchemy can recognize them as ORM models.
    """

    pass