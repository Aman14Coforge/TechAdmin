"""
Guardrails Package
Author: Amit Bhagat
Purpose: Validation layer that every request passes through before a tool runs.

Implements the guardrails design document for the Get User Details and Reset
Password use cases.

Modules:
    schemas             Decision and violation types shared by every check
    policy              Tunable values: allowlists, roles, limits, messages
    input_guardrails    Checks on the raw query, run before the LLM sees it
    authorization       Role checks, privileged accounts, rate limiting
    output_guardrails   Field filtering and redaction on the way out
    engine              Runs the checks in the order section 4.2 specifies
"""

from App.guardrails.engine import GuardrailEngine, audit, guardrail_engine
from App.guardrails.schemas import (
    GuardrailAction,
    GuardrailDecision,
    GuardrailViolation,
    ViolationCode,
)

__all__ = [
    "GuardrailEngine",
    "guardrail_engine",
    "audit",
    "GuardrailAction",
    "GuardrailDecision",
    "GuardrailViolation",
    "ViolationCode",
]
