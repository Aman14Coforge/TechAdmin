"""Authorization guardrails for TechAdmin."""
from __future__ import annotations

import time
from collections import defaultdict, deque
from typing import Deque, Dict, Optional

from App.guardrails.policy import (
    DEFAULT_ROLE, MSG_HIGH_PRIVILEGE, MSG_NOT_AUTHORIZED, MSG_RATE_LIMITED,
    PRIVILEGED_JOB_TITLES, PRIVILEGED_PATTERNS, PRIVILEGED_USERNAMES,
    RESET_RATE_LIMIT_COUNT, RESET_RATE_LIMIT_WINDOW_SECONDS, ROLE_PERMISSIONS,
)
from App.guardrails.schemas import (
    GuardrailAction, GuardrailDecision, GuardrailViolation,
    ViolationCode, allow, block,
)


def _local_part(identifier: str) -> str:
    return identifier.split("@", 1)[0].strip().lower() if identifier else ""


def is_privileged_account(identifier: str, job_title: str = None) -> Optional[str]:
    local = _local_part(identifier)
    if local in PRIVILEGED_USERNAMES:
        return f"username '{local}' is on the privileged account list"
    for pattern in PRIVILEGED_PATTERNS:
        if pattern in local:
            return f"username matches privileged pattern '{pattern}'"
    if job_title and job_title.strip().lower() in PRIVILEGED_JOB_TITLES:
        return f"job title '{job_title}' is high-privilege"
    return None


def check_authorization(intent: str, target_identifier: str, requester_id: str = None, requester_role: str = None) -> GuardrailDecision:
    role = (requester_role or DEFAULT_ROLE).strip().lower()
    permitted = ROLE_PERMISSIONS.get(role, set())
    if requester_id and target_identifier and _local_part(requester_id) == _local_part(target_identifier) and intent == "get_user_details":
        return allow()
    if intent not in permitted:
        return block(ViolationCode.NOT_AUTHORIZED, "Identity and Authorization Verification", MSG_NOT_AUTHORIZED, f"Role '{role}' is not permitted to run intent '{intent}'")
    return allow()


def check_high_privilege(intent: str, target_identifier: str, job_title: str = None) -> GuardrailDecision:
    if intent != "password_reset":
        return allow()
    reason = is_privileged_account(target_identifier, job_title)
    if not reason:
        return allow()
    return block(ViolationCode.HIGH_PRIVILEGE_ACCOUNT, "High-Privilege Account Protection", MSG_HIGH_PRIVILEGE, f"Target is privileged: {reason}")


class ResetRateLimiter:
    def __init__(self, max_attempts: int = RESET_RATE_LIMIT_COUNT, window_seconds: int = RESET_RATE_LIMIT_WINDOW_SECONDS) -> None:
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self._attempts: Dict[str, Deque[float]] = defaultdict(deque)

    def check(self, target_identifier: str) -> GuardrailDecision:
        key = _local_part(target_identifier)
        if not key:
            return allow()
        self._evict_expired(key)
        if len(self._attempts[key]) >= self.max_attempts:
            return block(ViolationCode.RATE_LIMITED, "Rate Limiting", MSG_RATE_LIMITED, f"{len(self._attempts[key])} resets within {self.window_seconds}s")
        return allow()

    def record(self, target_identifier: str) -> None:
        key = _local_part(target_identifier)
        if key:
            self._attempts[key].append(time.time())

    def _evict_expired(self, key: str) -> None:
        cutoff = time.time() - self.window_seconds
        while self._attempts[key] and self._attempts[key][0] < cutoff:
            self._attempts[key].popleft()


reset_rate_limiter = ResetRateLimiter()


def require_confirmation(intent: str, target_identifier: str) -> GuardrailDecision:
    labels = {
        "password_reset": "reset the password for",
        "revoke_access": "remove access from",
        "delete_user": "delete",
    }
    action_text = labels.get(intent, f"run '{intent}' against")
    return GuardrailDecision(
        action=GuardrailAction.REQUIRE_CONFIRMATION,
        message="This operation needs your confirmation before it can run.",
        confirmation_prompt=(
            f"You are about to {action_text} user:\n\n{target_identifier}\n\n"
            "Do you wish to proceed?"
        ),
        violations=[GuardrailViolation(
            code=ViolationCode.CONFIRMATION_REQUIRED,
            rule="Confirmation Requirement",
            detail=f"Awaiting user confirmation for {intent} on {target_identifier}",
        )],
    )
