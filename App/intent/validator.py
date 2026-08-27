"""
Purpose:
    Deterministic (non-LLM) validation of extracted metadata against the
    mandatory field list for a given intent.

Scope:
    Missing-field detection and is_valid computation only. The mandatory
    field list is defined in exactly one place in this file — the LLM's
    own opinion of what's missing (if it ever offered one) is never
    consulted or trusted.

Does not handle:
    Extraction itself (App/intent/metadata_extractor.py) or intent
    classification (App/intent/classifier.py).
"""
from __future__ import annotations

from App.schemas.extraction import ExtractedFields

# Mandatory fields per intent, defined once. Only "password_reset" is
# implemented for this MVP (per project scope); any other recognized
# intent (e.g. account_unlock, grant_access — both present in the
# existing Configs/intent_mapping.yaml) has no mandatory-field list here
# yet, so it is trivially reported as valid with nothing missing. That
# reflects "we have no field requirement defined for this intent," not
# "this intent is implemented and ready to execute" — those other flows
# are explicitly out of scope for this module.
MANDATORY_FIELDS_BY_INTENT: dict[str, list[str]] = {
    "password_reset": ["username", "email", "employee_id"],
}


def get_mandatory_fields(intent: str) -> list[str]:
    return MANDATORY_FIELDS_BY_INTENT.get(intent, [])


def validate_fields(intent: str, fields: ExtractedFields) -> tuple[list[str], bool]:
    """Returns (missing_fields, is_valid) computed purely from what
    `fields` actually contains — never inferred, never trusted from the
    LLM."""
    mandatory = get_mandatory_fields(intent)
    missing = [field for field in mandatory if getattr(fields, field, None) is None]
    return missing, len(missing) == 0
