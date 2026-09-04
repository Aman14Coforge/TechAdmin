"""
Pydantic Schemas Module
Author: Amit Bhagat
Purpose: Define validated data models for intent classification and metadata extraction.

The LLM returns free-form JSON. These models sit between the LLM and the rest of the
application so that whatever comes back is coerced into a known, safe shape:
  - intent is always one of the supported values
  - confidence is always a float between 0 and 1
  - metadata always has all four keys, with real None instead of the string "null"
"""

from enum import Enum
from typing import Any, Dict, Optional, Tuple

from loguru import logger
from pydantic import BaseModel, Field, field_validator


class SupportedIntent(str, Enum):
    """Intents this service can handle. 'unknown' is used for out-of-scope requests."""

    PASSWORD_RESET = "password_reset"
    ACCOUNT_UNLOCK = "account_unlock"
    GRANT_ACCESS = "grant_access"
    REVOKE_ACCESS = "revoke_access"
    GET_USER_DETAILS = "get_user_details"
    UNKNOWN = "unknown"


# Values that mean "nothing found" but would be truthy if kept as strings.
_NULLISH = {"", "null", "none", "n/a", "na", "unknown", "not found", "not provided"}


def coerce_intent(value: Any) -> SupportedIntent:
    """Map an LLM intent string onto SupportedIntent, defaulting to UNKNOWN."""
    if isinstance(value, SupportedIntent):
        return value
    if isinstance(value, str):
        try:
            return SupportedIntent(value.strip().lower())
        except ValueError:
            logger.warning(f"Unrecognised intent from LLM: {value}")
    return SupportedIntent.UNKNOWN


class UserMetadata(BaseModel):
    """Identifiers extracted from an IT support request. All fields are optional."""

    username: Optional[str] = Field(default=None, description="AD username, e.g. first.last")
    user_id: Optional[str] = Field(default=None, description="User or employee ID")
    email: Optional[str] = Field(default=None, description="Email address")
    employee_number: Optional[str] = Field(default=None, description="Employee number")

    @field_validator("username", "user_id", "email", "employee_number", mode="before")
    @classmethod
    def _clean(cls, value: Any) -> Optional[str]:
        """Convert empty values and 'null'-style strings into a real None."""
        if value is None:
            return None
        text = str(value).strip()
        if not text or text.lower() in _NULLISH:
            return None
        return text

    def to_dict(self) -> Dict[str, Optional[str]]:
        """Return the plain dict shape used by the agents and router."""
        return self.model_dump()


class IntentResult(BaseModel):
    """Result of intent classification only."""

    intent: SupportedIntent = SupportedIntent.UNKNOWN
    confidence: float = 0.0
    explanation: str = ""

    @field_validator("intent", mode="before")
    @classmethod
    def _validate_intent(cls, value: Any) -> SupportedIntent:
        return coerce_intent(value)

    @field_validator("confidence", mode="before")
    @classmethod
    def _validate_confidence(cls, value: Any) -> float:
        """Accept "0.95" or 95 and always return a float clamped to 0..1."""
        try:
            score = float(value)
        except (TypeError, ValueError):
            return 0.0
        if score > 1.0:
            score = score / 100.0 if score <= 100.0 else 1.0
        return max(0.0, min(1.0, score))

    @field_validator("explanation", mode="before")
    @classmethod
    def _validate_explanation(cls, value: Any) -> str:
        return "" if value is None else str(value)

    def to_dict(self) -> Dict[str, Any]:
        """Return the plain dict shape expected by existing callers."""
        return self.model_dump(mode="json")


class ExtractionResult(IntentResult):
    """Result of the unified call: intent plus metadata."""

    metadata: UserMetadata = Field(default_factory=UserMetadata)
    success: bool = False

    @field_validator("metadata", mode="before")
    @classmethod
    def _validate_metadata(cls, value: Any) -> Any:
        """Guard against the LLM omitting the metadata key or returning null."""
        return UserMetadata() if value is None else value


# Fields required per intent. Each inner tuple is an "at least one of" group.
INTENT_REQUIRED_FIELDS: Dict[SupportedIntent, Tuple[Tuple[str, ...], ...]] = {
    SupportedIntent.PASSWORD_RESET: (("username",),),
    SupportedIntent.ACCOUNT_UNLOCK: (("username", "email"),),
    SupportedIntent.GRANT_ACCESS: (("username", "email"),),
    SupportedIntent.REVOKE_ACCESS: (("username", "email"),),
    SupportedIntent.GET_USER_DETAILS: (("username", "email"),),
}


def validate_metadata(metadata: Any, intent: Any) -> Tuple[bool, str]:
    """
    Check that the metadata required by the given intent is present.

    Args:
        metadata: Extracted metadata (dict or UserMetadata)
        intent: The intent type (string or SupportedIntent)

    Returns:
        Tuple of (is_valid, message)
    """
    resolved = coerce_intent(intent)

    if isinstance(metadata, UserMetadata):
        data = metadata.to_dict()
    elif isinstance(metadata, dict):
        data = UserMetadata(**metadata).to_dict()
    else:
        data = {}

    if resolved is SupportedIntent.UNKNOWN:
        msg = "Request could not be matched to a supported IT support action"
        logger.warning(msg)
        return False, msg

    for group in INTENT_REQUIRED_FIELDS.get(resolved, ()):
        if not any(data.get(field) for field in group):
            msg = f"{' or '.join(group).capitalize()} is required for {resolved.value}"
            logger.warning(msg)
            return False, msg

    logger.info(f"Metadata validation passed for intent '{resolved.value}'")
    return True, "Metadata is valid"
