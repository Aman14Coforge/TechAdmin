# """
# Guardrail Engine
# Author: Amit Bhagat
# Purpose: The centralized validation layer from section 4 of the design document.

# Every request passes through here before a tool runs. The flow calls two
# methods, in this order:

#     validate_input(...)      before extraction
#     validate_request(...)    after extraction, before tool execution

# and one after the tool returns:

#     sanitize(...)            output filtering

# Keeping the sequence in one place is the point of section 4.1. If the order
# lived in demo_flow, a second caller such as the API routes would have to
# reproduce it, and the two would drift.
# """

# from __future__ import annotations

# from datetime import datetime
# from typing import Any, Dict, Optional

# from loguru import logger

# from App.guardrails.authorization import (
#     check_authorization,
#     check_high_privilege,
#     require_confirmation,
#     reset_rate_limiter,
# )
# from App.guardrails.input_guardrails import run_input_checks, validate_identifier
# from App.guardrails.output_guardrails import sanitize_response
# from App.guardrails.policy import (
#     ALLOWED_INTENTS,
#     CONFIRMATION_REQUIRED_INTENTS,
#     MSG_INVALID_INPUT,
#     MSG_NOT_SUPPORTED,
# )
# from App.guardrails.schemas import (
#     GuardrailDecision,
#     ViolationCode,
#     allow,
#     block,
# )


# def audit(
#     event: str,
#     request_id: str,
#     decision: GuardrailDecision = None,
#     **fields: Any,
# ) -> None:
#     """
#     Write one audit line.

#     Section 8 of the summary, the audit half. Every guardrail outcome is
#     recorded whether it passed or failed, because "no one was blocked today"
#     is only meaningful if passes are logged too.

#     Args:
#         event: The event name, e.g. GUARDRAIL_BLOCKED.
#         request_id: The request this concerns.
#         decision: The decision being recorded, if there is one.
#         **fields: Extra key/value pairs to include.
#     """
#     parts = [
#         f"event={event}",
#         f"request_id={request_id}",
#         f"timestamp={datetime.now().isoformat(timespec='milliseconds')}",
#     ]

#     if decision is not None:
#         parts.append(f"action={decision.action.value}")
#         for violation in decision.violations:
#             parts.append(f"rule={violation.rule}")
#             parts.append(f"code={violation.code.value}")
#             parts.append(f"detail={violation.detail}")

#     for key, value in fields.items():
#         parts.append(f"{key}={value}")

#     logger.info("GUARDRAIL_AUDIT | " + " | ".join(parts))


# class GuardrailEngine:
#     """Runs the guardrail checks in the order section 4.2 specifies."""

#     def validate_input(self, user_input: str, request_id: str) -> GuardrailDecision:
#         """
#         Run the checks that only need the raw query.

#         Called before extraction, so a prompt injection never reaches the model
#         and a pasted secret never enters its context.

#         Args:
#             user_input: The raw user query.
#             request_id: For the audit log.

#         Returns:
#             A GuardrailDecision.
#         """
#         decision = run_input_checks(user_input)

#         if decision.blocked:
#             audit("GUARDRAIL_INPUT_BLOCKED", request_id, decision)
#         else:
#             audit("GUARDRAIL_INPUT_PASSED", request_id, decision)

#         return decision

#     def validate_request(
#         self,
#         intent: str,
#         metadata: Dict[str, Any],
#         request_id: str,
#         requester_id: str = None,
#         requester_role: str = None,
#         job_title: str = None,
#         confirmed: bool = False,
#     ) -> GuardrailDecision:
#         """
#         Run the checks that need the extracted intent and metadata.

#         Order follows section 4.2: scope, then identifier format, then
#         authorization, then privileged-account protection, then rate limiting,
#         and confirmation last so the user is only asked once everything else
#         has passed.

#         Args:
#             intent: The resolved intent.
#             metadata: The extracted identifiers.
#             request_id: For the audit log.
#             requester_id: The authenticated caller, when known.
#             requester_role: The caller's role.
#             job_title: The target's job title from Graph, when known.
#             confirmed: True when the user has already confirmed this operation.

#         Returns:
#             A GuardrailDecision: allow, block, or require_confirmation.
#         """
#         metadata = metadata or {}

#         # --- Scope validation (1.1) ---
#         if intent in (None, "", "unknown"):
#             decision = block(
#                 code=ViolationCode.INTENT_UNKNOWN,
#                 rule="Query Scope Validation",
#                 message=MSG_NOT_SUPPORTED,
#                 detail="Intent could not be resolved",
#             )
#             audit("GUARDRAIL_BLOCKED", request_id, decision, intent=intent)
#             return decision

#         if intent not in ALLOWED_INTENTS:
#             decision = block(
#                 code=ViolationCode.INTENT_NOT_ALLOWED,
#                 rule="Query Scope Validation",
#                 message=MSG_NOT_SUPPORTED,
#                 detail=f"Intent '{intent}' is not in the allowlist {sorted(ALLOWED_INTENTS)}",
#             )
#             audit("GUARDRAIL_BLOCKED", request_id, decision, intent=intent)
#             return decision

#         # --- Identifier format validation (1.3) ---
#         decision = validate_identifier(
#             email=metadata.get("email"),
#             username=metadata.get("username"),
#             employee_number=metadata.get("employee_number"),
#         )
#         if decision.blocked:
#             audit("GUARDRAIL_BLOCKED", request_id, decision, intent=intent)
#             return decision

#         target = self.target_identifier(metadata)

#         if not target:
#             decision = block(
#                 code=ViolationCode.MISSING_TARGET_USER,
#                 rule="Input Format Validation",
#                 message=MSG_INVALID_INPUT,
#                 detail="No target user identifier was extracted",
#             )
#             audit("GUARDRAIL_BLOCKED", request_id, decision, intent=intent)
#             return decision

#         # --- Authorization (2.1 / 3.1) ---
#         decision = check_authorization(intent, target, requester_id, requester_role)
#         if decision.blocked:
#             audit("GUARDRAIL_BLOCKED", request_id, decision, intent=intent, target=target)
#             return decision

#         # --- High-privilege account protection (3.2) ---
#         decision = check_high_privilege(intent, target, job_title)
#         if decision.blocked:
#             audit("GUARDRAIL_BLOCKED", request_id, decision, intent=intent, target=target)
#             return decision

#         # --- Rate limiting (3.5) ---
#         if intent == "password_reset":
#             decision = reset_rate_limiter.check(target)
#             if decision.blocked:
#                 audit("GUARDRAIL_BLOCKED", request_id, decision, intent=intent, target=target)
#                 return decision

#         # --- Confirmation (3.4) ---
#         if intent in CONFIRMATION_REQUIRED_INTENTS and not confirmed:
#             decision = require_confirmation(intent, target)
#             audit("GUARDRAIL_CONFIRMATION_REQUIRED", request_id, decision,
#                   intent=intent, target=target)
#             return decision

#         audit("GUARDRAIL_PASSED", request_id, allow(), intent=intent, target=target)
#         return allow()

#     def sanitize(self, response: Dict[str, Any], intent: str = "") -> Dict[str, Any]:
#         """
#         Filter a completed response before it reaches the user.

#         Args:
#             response: The response dict built by the flow.
#             intent: The resolved intent.

#         Returns:
#             The sanitized response.
#         """
#         return sanitize_response(response, intent)

#     def record_reset(self, target_identifier: str) -> None:
#         """
#         Record a password reset that completed, for rate limiting.

#         Args:
#             target_identifier: The account that was reset.
#         """
#         reset_rate_limiter.record(target_identifier)

#     @staticmethod
#     def target_identifier(metadata: Dict[str, Any]) -> Optional[str]:
#         """
#         Pick the identifier that names the target account.

#         Email is preferred because it is unambiguous; username is the fallback.

#         Args:
#             metadata: The extracted identifiers.

#         Returns:
#             The identifier, or None when nothing usable was extracted.
#         """
#         for key in ("email", "username", "user_id", "employee_number"):
#             value = (metadata or {}).get(key)
#             if value:
#                 return str(value).strip()
#         return None


# # One shared engine for the process.
# guardrail_engine = GuardrailEngine()

"""
Guardrail Engine
Author: Amit Bhagat
Purpose: The centralized validation layer from section 4 of the design document.

Every request passes through here before a tool runs. The flow calls two
methods, in this order:

    validate_input(...)      before extraction
    validate_request(...)    after extraction, before tool execution

and one after the tool returns:

    sanitize(...)            output filtering

Keeping the sequence in one place is the point of section 4.1. If the order
lived in demo_flow, a second caller such as the API routes would have to
reproduce it, and the two would drift.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from loguru import logger

from App.guardrails.authorization import (
    check_authorization,
    check_high_privilege,
    require_confirmation,
    reset_rate_limiter,
)
from App.guardrails.input_guardrails import (
    # ADDED FOR FULL EMAIL REQUIREMENT (Amit Bhagat)
    check_extracted_email,
    run_input_checks,
    validate_identifier,
)
from App.guardrails.output_guardrails import sanitize_response
from App.guardrails.policy import (
    ALLOWED_INTENTS,
    CONFIRMATION_REQUIRED_INTENTS,
    MSG_INVALID_INPUT,
    MSG_NOT_SUPPORTED,
)
from App.guardrails.schemas import (
    GuardrailDecision,
    ViolationCode,
    allow,
    block,
)


def audit(
    event: str,
    request_id: str,
    decision: GuardrailDecision = None,
    **fields: Any,
) -> None:
    """
    Write one audit line.

    Section 8 of the summary, the audit half. Every guardrail outcome is
    recorded whether it passed or failed, because "no one was blocked today"
    is only meaningful if passes are logged too.

    Args:
        event: The event name, e.g. GUARDRAIL_BLOCKED.
        request_id: The request this concerns.
        decision: The decision being recorded, if there is one.
        **fields: Extra key/value pairs to include.
    """
    parts = [
        f"event={event}",
        f"request_id={request_id}",
        f"timestamp={datetime.now().isoformat(timespec='milliseconds')}",
    ]

    if decision is not None:
        parts.append(f"action={decision.action.value}")
        for violation in decision.violations:
            parts.append(f"rule={violation.rule}")
            parts.append(f"code={violation.code.value}")
            parts.append(f"detail={violation.detail}")

    for key, value in fields.items():
        parts.append(f"{key}={value}")

    logger.info("GUARDRAIL_AUDIT | " + " | ".join(parts))


class GuardrailEngine:
    """Runs the guardrail checks in the order section 4.2 specifies."""

    def validate_input(self, user_input: str, request_id: str) -> GuardrailDecision:
        """
        Run the checks that only need the raw query.

        Called before extraction, so a prompt injection never reaches the model
        and a pasted secret never enters its context.

        Args:
            user_input: The raw user query.
            request_id: For the audit log.

        Returns:
            A GuardrailDecision.
        """
        decision = run_input_checks(user_input)

        if decision.blocked:
            audit("GUARDRAIL_INPUT_BLOCKED", request_id, decision)
        else:
            audit("GUARDRAIL_INPUT_PASSED", request_id, decision)

        return decision

    def validate_request(
        self,
        intent: str,
        metadata: Dict[str, Any],
        request_id: str,
        requester_id: str = None,
        requester_role: str = None,
        job_title: str = None,
        confirmed: bool = False,
    ) -> GuardrailDecision:
        """
        Run the checks that need the extracted intent and metadata.

        Order follows section 4.2: scope, then identifier format, then
        authorization, then privileged-account protection, then rate limiting,
        and confirmation last so the user is only asked once everything else
        has passed.

        Args:
            intent: The resolved intent.
            metadata: The extracted identifiers.
            request_id: For the audit log.
            requester_id: The authenticated caller, when known.
            requester_role: The caller's role.
            job_title: The target's job title from Graph, when known.
            confirmed: True when the user has already confirmed this operation.

        Returns:
            A GuardrailDecision: allow, block, or require_confirmation.
        """
        metadata = metadata or {}

        # --- Scope validation (1.1) ---
        if intent in (None, "", "unknown"):
            decision = block(
                code=ViolationCode.INTENT_UNKNOWN,
                rule="Query Scope Validation",
                message=MSG_NOT_SUPPORTED,
                detail="Intent could not be resolved",
            )
            audit("GUARDRAIL_BLOCKED", request_id, decision, intent=intent)
            return decision

        if intent not in ALLOWED_INTENTS:
            decision = block(
                code=ViolationCode.INTENT_NOT_ALLOWED,
                rule="Query Scope Validation",
                message=MSG_NOT_SUPPORTED,
                detail=f"Intent '{intent}' is not in the allowlist {sorted(ALLOWED_INTENTS)}",
            )
            audit("GUARDRAIL_BLOCKED", request_id, decision, intent=intent)
            return decision

        # --- Identifier format validation (1.3) ---
        decision = validate_identifier(
            email=metadata.get("email"),
            username=metadata.get("username"),
            employee_number=metadata.get("employee_number"),
        )
        if decision.blocked:
            audit("GUARDRAIL_BLOCKED", request_id, decision, intent=intent)
            return decision

        # --- ADDED FOR FULL EMAIL REQUIREMENT (Amit Bhagat) ---
        # Both operations must name the target by complete email address. This
        # runs on the extracted metadata, so a query that mentioned an address
        # the model then reduced to a bare username is still refused.
        decision = check_extracted_email(metadata.get("email"))
        if decision.blocked:
            audit("GUARDRAIL_BLOCKED", request_id, decision, intent=intent)
            return decision
        # --- END ADDED FOR FULL EMAIL REQUIREMENT ---

        target = self.target_identifier(metadata)

        if not target:
            decision = block(
                code=ViolationCode.MISSING_TARGET_USER,
                rule="Input Format Validation",
                message=MSG_INVALID_INPUT,
                detail="No target user identifier was extracted",
            )
            audit("GUARDRAIL_BLOCKED", request_id, decision, intent=intent)
            return decision

        # --- Authorization (2.1 / 3.1) ---
        decision = check_authorization(intent, target, requester_id, requester_role)
        if decision.blocked:
            audit("GUARDRAIL_BLOCKED", request_id, decision, intent=intent, target=target)
            return decision

        # --- High-privilege account protection (3.2) ---
        decision = check_high_privilege(intent, target, job_title)
        if decision.blocked:
            audit("GUARDRAIL_BLOCKED", request_id, decision, intent=intent, target=target)
            return decision

        # --- Rate limiting (3.5) ---
        if intent == "password_reset":
            decision = reset_rate_limiter.check(target)
            if decision.blocked:
                audit("GUARDRAIL_BLOCKED", request_id, decision, intent=intent, target=target)
                return decision

        # --- Confirmation (3.4) ---
        if intent in CONFIRMATION_REQUIRED_INTENTS and not confirmed:
            decision = require_confirmation(intent, target)
            audit("GUARDRAIL_CONFIRMATION_REQUIRED", request_id, decision,
                  intent=intent, target=target)
            return decision

        audit("GUARDRAIL_PASSED", request_id, allow(), intent=intent, target=target)
        return allow()

    def sanitize(self, response: Dict[str, Any], intent: str = "") -> Dict[str, Any]:
        """
        Filter a completed response before it reaches the user.

        Args:
            response: The response dict built by the flow.
            intent: The resolved intent.

        Returns:
            The sanitized response.
        """
        return sanitize_response(response, intent)

    def record_reset(self, target_identifier: str) -> None:
        """
        Record a password reset that completed, for rate limiting.

        Args:
            target_identifier: The account that was reset.
        """
        reset_rate_limiter.record(target_identifier)

    @staticmethod
    def target_identifier(metadata: Dict[str, Any]) -> Optional[str]:
        """
        Pick the identifier that names the target account.

        Email is preferred because it is unambiguous; username is the fallback.

        Args:
            metadata: The extracted identifiers.

        Returns:
            The identifier, or None when nothing usable was extracted.
        """
        for key in ("email", "username", "user_id", "employee_number"):
            value = (metadata or {}).get(key)
            if value:
                return str(value).strip()
        return None


# One shared engine for the process.
guardrail_engine = GuardrailEngine()
