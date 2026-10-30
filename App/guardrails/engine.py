"""
Guardrail Engine
Author: Amit Bhagat

Purpose:
    Centralized request-validation layer.

Every request passes through:

    validate_input(...)
    validate_request(...)
    sanitize(...)

Password-reset behavior:
    - Requires one complete allowed company email
    - Requires one valid employee ID
    - Preserves the existing authorization, privileged-account,
      rate-limit, confirmation, and output-sanitization behavior
    - Does not impose password-reset-only requirements on other intents

Patch and Compliance Agent behavior remains isolated through PATCH_INTENTS.
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
    check_extracted_email,
    run_input_checks,
    validate_identifier,
)
from App.guardrails.output_guardrails import (
    sanitize_response,
)
from App.guardrails.policy import (
    ALLOWED_INTENTS,
    CONFIRMATION_REQUIRED_INTENTS,
    MSG_INVALID_INPUT,
    MSG_NOT_SUPPORTED,
    PATCH_INTENTS,
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
    Write one guardrail audit event.

    Sensitive values are not included by this function. Callers should pass
    only non-sensitive identifiers and policy metadata.
    """
    parts = [
        f"event={event}",
        f"request_id={request_id}",
        (
            "timestamp="
            + datetime.now().isoformat(
                timespec="milliseconds"
            )
        ),
    ]

    if decision is not None:
        parts.append(
            f"action={decision.action.value}"
        )

        for violation in decision.violations:
            parts.append(
                f"rule={violation.rule}"
            )
            parts.append(
                f"code={violation.code.value}"
            )
            parts.append(
                f"detail={violation.detail}"
            )

    for key, value in fields.items():
        parts.append(
            f"{key}={value}"
        )

    logger.info(
        "GUARDRAIL_AUDIT | "
        + " | ".join(parts)
    )


class GuardrailEngine:
    """Run all TechAdmin safety checks in a deterministic order."""

    def validate_input(
        self,
        user_input: str,
        request_id: str,
    ) -> GuardrailDecision:
        """
        Run checks that need only the raw query.

        Complete email is not required here because the request intent has not
        yet been extracted.
        """
        decision = run_input_checks(
            user_input
        )

        if decision.blocked:
            audit(
                "GUARDRAIL_INPUT_BLOCKED",
                request_id,
                decision,
            )
        else:
            audit(
                "GUARDRAIL_INPUT_PASSED",
                request_id,
                decision,
            )

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
        Validate a request after intent and metadata extraction.

        Request-validation order:
            1. Intent allowlist
            2. Patch request path, when applicable
            3. Identifier format
            4. Password-reset verification metadata requirements
            5. Target resolution
            6. Authorization
            7. Privileged-account protection
            8. Reset rate limiting
            9. Confirmation
        """
        metadata = metadata or {}

        # ------------------------------------------------------------------
        # Intent scope validation
        # ------------------------------------------------------------------

        if intent in (
            None,
            "",
            "unknown",
        ):
            decision = block(
                code=ViolationCode.INTENT_UNKNOWN,
                rule="Query Scope Validation",
                message=MSG_NOT_SUPPORTED,
                detail=(
                    "Intent could not be resolved"
                ),
            )

            audit(
                "GUARDRAIL_BLOCKED",
                request_id,
                decision,
                intent=intent,
            )

            return decision

        if intent not in ALLOWED_INTENTS:
            decision = block(
                code=ViolationCode.INTENT_NOT_ALLOWED,
                rule="Query Scope Validation",
                message=MSG_NOT_SUPPORTED,
                detail=(
                    f"Intent '{intent}' is not "
                    "in the configured allowlist"
                ),
            )

            audit(
                "GUARDRAIL_BLOCKED",
                request_id,
                decision,
                intent=intent,
            )

            return decision

        # ------------------------------------------------------------------
        # Patch Agent has its own metadata and validation path.
        # ------------------------------------------------------------------

        if intent in PATCH_INTENTS:
            return self._validate_patch_request(
                intent=intent,
                metadata=metadata,
                request_id=request_id,
                requester_id=requester_id,
                requester_role=requester_role,
                confirmed=confirmed,
            )

        # ------------------------------------------------------------------
        # General Identity identifier validation
        # ------------------------------------------------------------------

        decision = validate_identifier(
            email=metadata.get("email"),
            username=metadata.get(
                "username"
            ),
            employee_number=metadata.get(
                "employee_number"
            ),
        )

        if decision.blocked:
            audit(
                "GUARDRAIL_BLOCKED",
                request_id,
                decision,
                intent=intent,
            )

            return decision

        # ------------------------------------------------------------------
        # Password-reset-only verification requirements
        # ------------------------------------------------------------------

        if intent == "password_reset":
            decision = check_extracted_email(
                metadata.get("email")
            )

            if decision.blocked:
                audit(
                    "GUARDRAIL_BLOCKED",
                    request_id,
                    decision,
                    intent=intent,
                )

                return decision

            employee_number = str(
                metadata.get(
                    "employee_number"
                )
                or ""
            ).strip()

            if not employee_number:
                decision = block(
                    code=(
                        ViolationCode.INVALID_IDENTIFIER
                    ),
                    rule=(
                        "Password Reset Identity "
                        "Verification"
                    ),
                    message=(
                        "Please provide the employee ID "
                        "to verify the user before resetting "
                        "the password."
                    ),
                    detail=(
                        "Password-reset request did not "
                        "contain employee_number"
                    ),
                )

                audit(
                    "GUARDRAIL_BLOCKED",
                    request_id,
                    decision,
                    intent=intent,
                )

                return decision

        # ------------------------------------------------------------------
        # Resolve one target identifier
        # ------------------------------------------------------------------

        target = self.target_identifier(
            metadata
        )

        if not target:
            decision = block(
                code=ViolationCode.MISSING_TARGET_USER,
                rule="Input Format Validation",
                message=MSG_INVALID_INPUT,
                detail=(
                    "No target user identifier "
                    "was extracted"
                ),
            )

            audit(
                "GUARDRAIL_BLOCKED",
                request_id,
                decision,
                intent=intent,
            )

            return decision

        # ------------------------------------------------------------------
        # Authorization
        # ------------------------------------------------------------------

        decision = check_authorization(
            intent,
            target,
            requester_id,
            requester_role,
        )

        if decision.blocked:
            audit(
                "GUARDRAIL_BLOCKED",
                request_id,
                decision,
                intent=intent,
                target=target,
            )

            return decision

        # ------------------------------------------------------------------
        # High-privilege target protection
        # ------------------------------------------------------------------

        decision = check_high_privilege(
            intent,
            target,
            job_title,
        )

        if decision.blocked:
            audit(
                "GUARDRAIL_BLOCKED",
                request_id,
                decision,
                intent=intent,
                target=target,
            )

            return decision

        # ------------------------------------------------------------------
        # Password-reset rate limiting
        # ------------------------------------------------------------------

        if intent == "password_reset":
            decision = reset_rate_limiter.check(
                target
            )

            if decision.blocked:
                audit(
                    "GUARDRAIL_BLOCKED",
                    request_id,
                    decision,
                    intent=intent,
                    target=target,
                )

                return decision

        # ------------------------------------------------------------------
        # Trusted confirmation
        # ------------------------------------------------------------------

        if (
            intent in CONFIRMATION_REQUIRED_INTENTS
            and not confirmed
        ):
            decision = require_confirmation(
                intent,
                target,
            )

            audit(
                "GUARDRAIL_CONFIRMATION_REQUIRED",
                request_id,
                decision,
                intent=intent,
                target=target,
            )

            return decision

        passed = allow()

        audit(
            "GUARDRAIL_PASSED",
            request_id,
            passed,
            intent=intent,
            target=target,
        )

        return passed

    def _validate_patch_request(
        self,
        *,
        intent: str,
        metadata: Dict[str, Any],
        request_id: str,
        requester_id: str | None,
        requester_role: str | None,
        confirmed: bool,
    ) -> GuardrailDecision:
        """
        Preserve the existing Compliance Agent validation path.
        """
        import re

        device = metadata.get(
            "device_name"
        )

        target = (
            str(device).strip()
            if device
            else "patch compliance fleet"
        )

        decision = check_authorization(
            intent,
            target,
            requester_id,
            requester_role,
        )

        if (
            not decision.blocked
            and device
            and (
                not isinstance(device, str)
                or not re.fullmatch(
                    r"[A-Za-z0-9]"
                    r"[A-Za-z0-9_.-]{0,252}",
                    device.strip(),
                )
            )
        ):
            decision = block(
                code=ViolationCode.INVALID_IDENTIFIER,
                rule="Patch Device Validation",
                message=(
                    "Please provide one valid "
                    "device name."
                ),
                detail=(
                    "The patch device identifier "
                    "has an invalid format."
                ),
            )

        if (
            not decision.blocked
            and intent == "patch_ticket"
            and not device
        ):
            decision = block(
                code=ViolationCode.INVALID_IDENTIFIER,
                rule="Patch Device Validation",
                message=(
                    "Please provide the device name "
                    "for the patch ticket."
                ),
                detail=(
                    "Ticket creation requires "
                    "a specific device."
                ),
            )

        if (
            not decision.blocked
            and not confirmed
            and (
                intent == "patch_ticket"
                or intent
                in CONFIRMATION_REQUIRED_INTENTS
            )
        ):
            decision = require_confirmation(
                intent,
                target,
            )

        if decision.blocked:
            event = "GUARDRAIL_BLOCKED"

        elif decision.needs_confirmation:
            event = (
                "GUARDRAIL_CONFIRMATION_REQUIRED"
            )

        else:
            event = "GUARDRAIL_PASSED"

        audit(
            event,
            request_id,
            decision,
            intent=intent,
            target=target,
        )

        return decision

    def sanitize(
        self,
        response: Dict[str, Any],
        intent: str = "",
    ) -> Dict[str, Any]:
        """Filter completed output before returning it to the caller."""
        return sanitize_response(
            response,
            intent,
        )

    def record_reset(
        self,
        target_identifier: str,
    ) -> None:
        """Record a successful password reset for rate limiting."""
        if target_identifier:
            reset_rate_limiter.record(
                target_identifier
            )

    @staticmethod
    def target_identifier(
        metadata: Dict[str, Any],
    ) -> Optional[str]:
        """
        Select the target account identifier.

        Email is preferred because password reset must use the complete email.
        Existing operations retain username and user-ID fallback behavior.
        Employee ID remains a final fallback for investigation-related requests.
        """
        for key in (
            "email",
            "username",
            "user_id",
            "employee_number",
        ):
            value = (
                metadata or {}
            ).get(key)

            if value:
                normalized = str(
                    value
                ).strip()

                if normalized:
                    return normalized

        return None


guardrail_engine = GuardrailEngine()