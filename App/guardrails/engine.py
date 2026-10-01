"""Centralized guardrail engine for TechAdmin."""
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
    """Run raw-input, request, authorization, and output guardrails."""

    def validate_input(
        self,
        user_input: str,
        request_id: str,
    ) -> GuardrailDecision:
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
        metadata = metadata or {}
        normalized_intent = str(
            getattr(intent, "value", intent) or ""
        ).strip().casefold()

        # Scope validation.
        if normalized_intent in ("", "unknown"):
            decision = block(
                code=ViolationCode.INTENT_UNKNOWN,
                rule="Query Scope Validation",
                message=MSG_NOT_SUPPORTED,
                detail="Intent could not be resolved",
            )
            audit(
                "GUARDRAIL_BLOCKED",
                request_id,
                decision,
                intent=normalized_intent,
            )
            return decision

        if normalized_intent not in ALLOWED_INTENTS:
            decision = block(
                code=ViolationCode.INTENT_NOT_ALLOWED,
                rule="Query Scope Validation",
                message=MSG_NOT_SUPPORTED,
                detail=(
                    f"Intent '{normalized_intent}' is not in the allowlist "
                    f"{sorted(ALLOWED_INTENTS)}"
                ),
            )
            audit(
                "GUARDRAIL_BLOCKED",
                request_id,
                decision,
                intent=normalized_intent,
            )
            return decision

        # Identifier validation. Computer lookup validates hostname; all
        # existing user operations retain their identifier validation.
        decision = validate_identifier(
            email=metadata.get("email"),
            username=metadata.get("username"),
            employee_number=metadata.get("employee_number"),
            hostname=metadata.get("hostname"),
            intent=normalized_intent,
        )
        if decision.blocked:
            audit(
                "GUARDRAIL_BLOCKED",
                request_id,
                decision,
                intent=normalized_intent,
            )
            return decision

        # Full email is still mandatory for user operations. For the computer
        # lookup, one valid hostname satisfies this target guardrail.
        decision = check_extracted_email(
            email=metadata.get("email"),
            intent=normalized_intent,
            hostname=metadata.get("hostname"),
        )
        if decision.blocked:
            audit(
                "GUARDRAIL_BLOCKED",
                request_id,
                decision,
                intent=normalized_intent,
            )
            return decision

        target = self.target_identifier(
            metadata,
            intent=normalized_intent,
        )

        if not target:
            target_type = (
                "computer identifier"
                if normalized_intent == "get_computer_details"
                else "user identifier"
            )
            decision = block(
                code=ViolationCode.MISSING_TARGET_USER,
                rule="Input Format Validation",
                message=MSG_INVALID_INPUT,
                detail=f"No target {target_type} was extracted",
            )
            audit(
                "GUARDRAIL_BLOCKED",
                request_id,
                decision,
                intent=normalized_intent,
            )
            return decision

        decision = check_authorization(
            normalized_intent,
            target,
            requester_id,
            requester_role,
        )
        if decision.blocked:
            audit(
                "GUARDRAIL_BLOCKED",
                request_id,
                decision,
                intent=normalized_intent,
                target=target,
            )
            return decision

        decision = check_high_privilege(
            normalized_intent,
            target,
            job_title,
        )
        if decision.blocked:
            audit(
                "GUARDRAIL_BLOCKED",
                request_id,
                decision,
                intent=normalized_intent,
                target=target,
            )
            return decision

        if normalized_intent == "password_reset":
            decision = reset_rate_limiter.check(target)
            if decision.blocked:
                audit(
                    "GUARDRAIL_BLOCKED",
                    request_id,
                    decision,
                    intent=normalized_intent,
                    target=target,
                )
                return decision

        if (
            normalized_intent in CONFIRMATION_REQUIRED_INTENTS
            and not confirmed
        ):
            decision = require_confirmation(normalized_intent, target)
            audit(
                "GUARDRAIL_CONFIRMATION_REQUIRED",
                request_id,
                decision,
                intent=normalized_intent,
                target=target,
            )
            return decision

        audit(
            "GUARDRAIL_PASSED",
            request_id,
            allow(),
            intent=normalized_intent,
            target=target,
        )
        return allow()

    def sanitize(
        self,
        response: Dict[str, Any],
        intent: str = "",
    ) -> Dict[str, Any]:
        return sanitize_response(response, intent)

    def record_reset(self, target_identifier: str) -> None:
        reset_rate_limiter.record(target_identifier)

    @staticmethod
    def target_identifier(
        metadata: Dict[str, Any],
        intent: str = "",
    ) -> Optional[str]:
        metadata = metadata or {}

        if intent == "get_computer_details":
            hostname = metadata.get("hostname")
            return str(hostname).strip() if hostname else None

        for key in ("email", "username", "user_id", "employee_number"):
            value = metadata.get(key)
            if value:
                return str(value).strip()

        return None


guardrail_engine = GuardrailEngine()
