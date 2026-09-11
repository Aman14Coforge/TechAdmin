"""
Guardrail Schemas
Author: Amit Bhagat
Purpose: The shared vocabulary every guardrail check speaks.

A check never raises and never returns a bare bool. It returns a
GuardrailDecision, which carries three things:

  - whether the request may continue
  - a message safe to show the end user
  - a violation code and detail for the audit log

Keeping the user-facing message separate from the audit detail is deliberate.
The user is told "Requested operation is currently not supported."; the log
records exactly which rule fired and why. Telling the user which rule blocked
them, and what it was looking for, is a map for getting around it.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class GuardrailAction(str, Enum):
    """What the engine decided to do with a request."""

    ALLOW = "allow"
    BLOCK = "block"
    # The request is legitimate but needs a human to say yes first. Used for
    # password resets, and for privileged accounts that need extra approval.
    REQUIRE_CONFIRMATION = "require_confirmation"


class ViolationCode(str, Enum):
    """
    Stable identifiers for each rule.

    These are written to the audit log and are safe to grep. They are separate
    from the user-facing message so the message can be reworded without
    breaking log analysis.
    """

    # Input guardrails
    SECRET_IN_INPUT = "secret_in_input"
    PROMPT_INJECTION = "prompt_injection"
    INVALID_IDENTIFIER = "invalid_identifier"
    MULTIPLE_USERS = "multiple_users"
    BULK_ENUMERATION = "bulk_enumeration"

    # Scope guardrails
    INTENT_NOT_ALLOWED = "intent_not_allowed"
    INTENT_UNKNOWN = "intent_unknown"
    MISSING_TARGET_USER = "missing_target_user"

    # Authorization guardrails
    NOT_AUTHORIZED = "not_authorized"
    HIGH_PRIVILEGE_ACCOUNT = "high_privilege_account"
    RATE_LIMITED = "rate_limited"

    # Confirmation
    CONFIRMATION_REQUIRED = "confirmation_required"

    # Output guardrails
    SENSITIVE_FIELD_REMOVED = "sensitive_field_removed"


class GuardrailViolation(BaseModel):
    """One rule that fired, recorded for the audit log."""

    code: ViolationCode
    rule: str = Field(description="Human readable rule name, e.g. 'Single User Validation'")
    detail: str = Field(default="", description="Why it fired. Audit log only, never shown to the user.")


class GuardrailDecision(BaseModel):
    """
    The outcome of running one check, or of the whole engine.

    Attributes:
        action: allow, block, or require_confirmation
        message: Safe to show the user. Deliberately non-specific on blocks.
        violations: Every rule that fired, for the audit log.
        sanitized_input: The user input after redaction, if anything was redacted.
        confirmation_prompt: The question to put to the user, when confirmation is needed.
    """

    action: GuardrailAction = GuardrailAction.ALLOW
    message: str = ""
    violations: List[GuardrailViolation] = Field(default_factory=list)
    sanitized_input: Optional[str] = None
    confirmation_prompt: Optional[str] = None

    @property
    def allowed(self) -> bool:
        """True when the request may proceed to tool execution."""
        return self.action == GuardrailAction.ALLOW

    @property
    def blocked(self) -> bool:
        """True when the request must not proceed."""
        return self.action == GuardrailAction.BLOCK

    @property
    def needs_confirmation(self) -> bool:
        """True when the request is waiting on a human yes."""
        return self.action == GuardrailAction.REQUIRE_CONFIRMATION

    def to_dict(self) -> Dict[str, Any]:
        """Plain dict for the response payload and the audit log."""
        return {
            "action": self.action.value,
            "allowed": self.allowed,
            "message": self.message,
            "violations": [v.model_dump(mode="json") for v in self.violations],
            "confirmation_prompt": self.confirmation_prompt,
        }


def allow() -> GuardrailDecision:
    """Shorthand for a check that found nothing wrong."""
    return GuardrailDecision(action=GuardrailAction.ALLOW)


def block(
    code: ViolationCode,
    rule: str,
    message: str,
    detail: str = "",
) -> GuardrailDecision:
    """
    Shorthand for a check that failed.

    Args:
        code: The stable violation code, for the audit log.
        rule: The rule name from the guardrails design document.
        message: What the user sees. Keep it generic.
        detail: What the log records. May be specific.
    """
    return GuardrailDecision(
        action=GuardrailAction.BLOCK,
        message=message,
        violations=[GuardrailViolation(code=code, rule=rule, detail=detail)],
    )
