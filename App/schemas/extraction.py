"""
Purpose:
    Pydantic schema for the fields extracted from a user query
    (username/email/employee_id).

Scope:
    Data representation and field-level normalization only — blank
    strings and malformed emails degrade to None rather than raising, so
    a slightly-off LLM response never crashes the pipeline.

Does not handle:
    Deciding which fields are mandatory or computing missing_fields /
    is_valid — that is deterministic logic owned by
    App/intent/validator.py, not this schema.
"""
from __future__ import annotations

import re

from pydantic import BaseModel, field_validator

# Deliberately a plain regex rather than pydantic's EmailStr, to avoid
# adding the email-validator package as a new dependency on top of the
# existing, unmodified requirements.txt (see requirements-additional.txt
# for the one dependency this module DOES require beyond it).
_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class ExtractedFields(BaseModel):
    """Exactly what the model extracted — never inferred, never
    invented."""

    username: str | None = None
    email: str | None = None
    employee_id: str | None = None

    @field_validator("username", "employee_id", mode="before")
    @classmethod
    def _blank_to_none(cls, value):
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("email", mode="before")
    @classmethod
    def _blank_or_malformed_email_to_none(cls, value):
        """A malformed or blank email is treated as "not usably provided"
        rather than raising — the validator will then correctly report it
        as missing instead of the pipeline crashing on it."""
        if not isinstance(value, str) or not value.strip():
            return None
        return value.strip() if _EMAIL_PATTERN.match(value.strip()) else None
