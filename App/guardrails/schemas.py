"""Shared guardrail decision and violation contracts."""
from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class GuardrailAction(str, Enum):
    ALLOW = "allow"
    BLOCK = "block"
    REQUIRE_CONFIRMATION = "require_confirmation"


class ViolationCode(str, Enum):
    SECRET_IN_INPUT = "secret_in_input"
    PROMPT_INJECTION = "prompt_injection"
    INVALID_IDENTIFIER = "invalid_identifier"
    MULTIPLE_USERS = "multiple_users"
    BULK_ENUMERATION = "bulk_enumeration"

    INTENT_NOT_ALLOWED = "intent_not_allowed"
    INTENT_UNKNOWN = "intent_unknown"
    # Retained for backward compatibility. The engine now uses it for a missing
    # target of either type, while the audit detail identifies user/computer.
    MISSING_TARGET_USER = "missing_target_user"

    NOT_AUTHORIZED = "not_authorized"
    HIGH_PRIVILEGE_ACCOUNT = "high_privilege_account"
    RATE_LIMITED = "rate_limited"

    CONFIRMATION_REQUIRED = "confirmation_required"
    SENSITIVE_FIELD_REMOVED = "sensitive_field_removed"


class GuardrailViolation(BaseModel):
    code: ViolationCode
    rule: str = Field(
        description="Human readable rule name, e.g. 'Single User Validation'"
    )
    detail: str = Field(
        default="",
        description="Why it fired. Audit log only, never shown to the user.",
    )


class GuardrailDecision(BaseModel):
    action: GuardrailAction = GuardrailAction.ALLOW
    message: str = ""
    violations: List[GuardrailViolation] = Field(default_factory=list)
    sanitized_input: Optional[str] = None
    confirmation_prompt: Optional[str] = None

    @property
    def allowed(self) -> bool:
        return self.action == GuardrailAction.ALLOW

    @property
    def blocked(self) -> bool:
        return self.action == GuardrailAction.BLOCK

    @property
    def needs_confirmation(self) -> bool:
        return self.action == GuardrailAction.REQUIRE_CONFIRMATION

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action": self.action.value,
            "allowed": self.allowed,
            "message": self.message,
            "violations": [
                violation.model_dump(mode="json")
                for violation in self.violations
            ],
            "confirmation_prompt": self.confirmation_prompt,
        }


def allow() -> GuardrailDecision:
    return GuardrailDecision(action=GuardrailAction.ALLOW)


def block(
    code: ViolationCode,
    rule: str,
    message: str,
    detail: str = "",
) -> GuardrailDecision:
    return GuardrailDecision(
        action=GuardrailAction.BLOCK,
        message=message,
        violations=[
            GuardrailViolation(
                code=code,
                rule=rule,
                detail=detail,
            )
        ],
    )
