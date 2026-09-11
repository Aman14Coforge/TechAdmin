"""
Authorization Guardrails
Author: Amit Bhagat
Purpose: Who is allowed to do what, and to whom.

Covers sections 2.1, 3.1, 3.2 and 3.5 of the guardrails design document:

  - role-based authorization, with self-lookup always permitted
  - high-privilege account protection
  - password reset rate limiting

A note on what this is and is not. Real authorization needs an authenticated
caller; this module takes the caller's identity as an argument and trusts it.
That is correct for a layer that sits behind authentication, and wrong as a
standalone security boundary. Until the API layer authenticates the caller, the
default role in policy.py is what actually decides, so it is set to the least
privileged value that still lets the demo run.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque
from typing import Deque, Dict, Optional

from loguru import logger

from App.guardrails.policy import (
    DEFAULT_ROLE,
    MSG_HIGH_PRIVILEGE,
    MSG_NOT_AUTHORIZED,
    MSG_RATE_LIMITED,
    PRIVILEGED_JOB_TITLES,
    PRIVILEGED_PATTERNS,
    PRIVILEGED_USERNAMES,
    RESET_RATE_LIMIT_COUNT,
    RESET_RATE_LIMIT_WINDOW_SECONDS,
    ROLE_PERMISSIONS,
)
from App.guardrails.schemas import (
    GuardrailAction,
    GuardrailDecision,
    GuardrailViolation,
    ViolationCode,
    allow,
    block,
)


def _local_part(identifier: str) -> str:
    """Return the username portion of an email, or the identifier unchanged."""
    return identifier.split("@", 1)[0].strip().lower() if identifier else ""


def is_privileged_account(identifier: str, job_title: str = None) -> Optional[str]:
    """
    Decide whether a target account is high-privilege.

    Section 3.2. Three signals, checked in order of confidence:

      1. the username is on the explicit list
      2. the username contains a privileged naming pattern
      3. the job title from Graph is on the privileged titles list

    The job title check is what catches "Reset CEO password" when the account
    is named something ordinary like sarah.mitchell.

    Args:
        identifier: Username or email of the target account.
        job_title: The target's job title from Graph, when it is known.

    Returns:
        The reason it is privileged, or None if it is not.
    """
    local = _local_part(identifier)

    if local in PRIVILEGED_USERNAMES:
        return f"username '{local}' is on the privileged account list"

    for pattern in PRIVILEGED_PATTERNS:
        if pattern in local:
            return f"username matches privileged pattern '{pattern}'"

    if job_title and job_title.strip().lower() in PRIVILEGED_JOB_TITLES:
        return f"job title '{job_title}' is high-privilege"

    return None


def check_authorization(
    intent: str,
    target_identifier: str,
    requester_id: str = None,
    requester_role: str = None,
) -> GuardrailDecision:
    """
    Check whether the requester may run this intent against this target.

    Sections 2.1 and 3.1. Self-lookup is always allowed regardless of role, so
    an employee can read their own record; everything else is decided by the
    role's permission set.

    Args:
        intent: The intent being requested, e.g. "password_reset".
        target_identifier: The account being acted on.
        requester_id: The authenticated caller, when one is known.
        requester_role: The caller's role. Falls back to the configured default.

    Returns:
        A GuardrailDecision. Blocks when the role lacks the permission.
    """
    role = (requester_role or DEFAULT_ROLE).strip().lower()
    permitted = ROLE_PERMISSIONS.get(role, set())

    # Self-lookup: reading your own record needs no special role.
    if (
        requester_id
        and target_identifier
        and _local_part(requester_id) == _local_part(target_identifier)
        and intent == "get_user_details"
    ):
        return allow()

    if intent not in permitted:
        return block(
            code=ViolationCode.NOT_AUTHORIZED,
            rule="Identity and Authorization Verification",
            message=MSG_NOT_AUTHORIZED,
            detail=f"Role '{role}' is not permitted to run intent '{intent}'",
        )

    return allow()


def check_high_privilege(
    intent: str,
    target_identifier: str,
    job_title: str = None,
) -> GuardrailDecision:
    """
    Require extra approval before modifying a privileged account.

    Section 3.2. Reads are unaffected; this only gates operations that change
    an account, which today means password_reset.

    Args:
        intent: The intent being requested.
        target_identifier: The account being acted on.
        job_title: The target's job title from Graph, when known.

    Returns:
        A GuardrailDecision. Blocks when the target is privileged.
    """
    if intent != "password_reset":
        return allow()

    reason = is_privileged_account(target_identifier, job_title)
    if not reason:
        return allow()

    return block(
        code=ViolationCode.HIGH_PRIVILEGE_ACCOUNT,
        rule="High-Privilege Account Protection",
        message=MSG_HIGH_PRIVILEGE,
        detail=f"Target is privileged: {reason}",
    )


class ResetRateLimiter:
    """
    Sliding-window rate limiter for password resets.

    Section 3.5. Keyed by target account, so repeatedly resetting one user is
    limited while unrelated resets are not affected.

    In-process and not shared between workers, which is fine for the demo and
    for a single Streamlit session. A multi-worker deployment needs this in
    Redis or the database instead, or each worker enforces its own separate
    limit and the effective limit is the configured one times the worker count.
    """

    def __init__(
        self,
        max_attempts: int = RESET_RATE_LIMIT_COUNT,
        window_seconds: int = RESET_RATE_LIMIT_WINDOW_SECONDS,
    ) -> None:
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self._attempts: Dict[str, Deque[float]] = defaultdict(deque)

    def check(self, target_identifier: str) -> GuardrailDecision:
        """
        Check the limit without consuming an attempt.

        Args:
            target_identifier: The account being reset.

        Returns:
            A GuardrailDecision. Blocks when the window is full.
        """
        key = _local_part(target_identifier)
        if not key:
            return allow()

        self._evict_expired(key)

        if len(self._attempts[key]) >= self.max_attempts:
            return block(
                code=ViolationCode.RATE_LIMITED,
                rule="Rate Limiting",
                message=MSG_RATE_LIMITED,
                detail=(
                    f"{len(self._attempts[key])} resets for this account "
                    f"within {self.window_seconds}s"
                ),
            )

        return allow()

    def record(self, target_identifier: str) -> None:
        """
        Record a reset that actually happened.

        Called after the tool succeeds rather than when the request arrives, so
        a reset that was blocked or that failed does not count against the user.

        Args:
            target_identifier: The account that was reset.
        """
        key = _local_part(target_identifier)
        if key:
            self._attempts[key].append(time.time())

    def _evict_expired(self, key: str) -> None:
        """Drop timestamps that have fallen out of the window."""
        cutoff = time.time() - self.window_seconds
        attempts = self._attempts[key]
        while attempts and attempts[0] < cutoff:
            attempts.popleft()


# One shared limiter for the process.
reset_rate_limiter = ResetRateLimiter()


def require_confirmation(intent: str, target_identifier: str) -> GuardrailDecision:
    """
    Build the confirmation request for a sensitive operation.

    Section 3.4. Returns a REQUIRE_CONFIRMATION decision rather than a block,
    because the request is legitimate and is only waiting on a human yes.

    Args:
        intent: The intent being requested.
        target_identifier: The account being acted on.

    Returns:
        A GuardrailDecision carrying the question to put to the user.
    """
    return GuardrailDecision(
        action=GuardrailAction.REQUIRE_CONFIRMATION,
        message="This operation needs your confirmation before it can run.",
        confirmation_prompt=(
            f"You are about to reset the password for user:\n\n"
            f"{target_identifier}\n\nDo you wish to proceed?"
        ),
        violations=[
            GuardrailViolation(
                code=ViolationCode.CONFIRMATION_REQUIRED,
                rule="Confirmation Requirement",
                detail=f"Awaiting user confirmation for {intent} on {target_identifier}",
            )
        ],
    )
