"""
Input Guardrails
Author: Amit Bhagat

Purpose:
    Checks that run on the raw user query before the LLM sees it.

Covers:
    - Secrets and personal data in the query
    - Prompt injection attempts
    - Identifier format validation
    - Single target user
    - Bulk enumeration attempts
    - Forbidden operations

Important behavior:
    Complete email is not required during raw intent-independent validation.
    The request intent is not known yet at this stage.

    After extraction, engine.py applies complete-email and employee-ID
    requirements specifically to password_reset. Other Identity operations
    retain their existing identifier behavior.
"""

from __future__ import annotations

import re
from typing import List, Tuple

from loguru import logger

from App.guardrails.policy import (
    ALLOWED_EMAIL_DOMAINS,
    FORBIDDEN_OPERATION_PATTERNS,
    MSG_DOMAIN_NOT_ALLOWED,
    MSG_FULL_EMAIL_REQUIRED,
    MSG_INVALID_INPUT,
    MSG_NOT_SUPPORTED,
    MSG_SINGLE_USER,
    REQUIRE_FULL_EMAIL,
)
from App.guardrails.schemas import (
    GuardrailDecision,
    ViolationCode,
    allow,
    block,
)


# ---------------------------------------------------------------------------
# Identifier patterns
# ---------------------------------------------------------------------------

EMAIL_PATTERN = re.compile(
    r"[A-Za-z0-9._%+\-]+@"
    r"[A-Za-z0-9.\-]+\."
    r"[A-Za-z]{2,}"
)

USERNAME_PATTERN = re.compile(
    r"^[A-Za-z0-9]"
    r"(?:[A-Za-z0-9._\-]{0,62}[A-Za-z0-9])?$"
)

EMPLOYEE_ID_PATTERN = re.compile(
    r"^[A-Za-z0-9]"
    r"[A-Za-z0-9._\-]{1,31}$"
)


# ---------------------------------------------------------------------------
# Sensitive input patterns
# ---------------------------------------------------------------------------

SECRET_PATTERNS: List[
    Tuple[str, re.Pattern]
] = [
    (
        "password_assignment",
        re.compile(
            r"(?:password|passwd|pwd)\s*"
            r"(?:is|=|:)\s*\S{4,}",
            re.IGNORECASE,
        ),
    ),
    (
        "api_key",
        re.compile(
            r"(?:api[_\-\s]?key|apikey)\s*"
            r"(?:is|=|:)?\s*"
            r"[A-Za-z0-9_\-]{16,}",
            re.IGNORECASE,
        ),
    ),
    (
        "bearer_token",
        re.compile(
            r"\bBearer\s+"
            r"[A-Za-z0-9._\-]{20,}",
            re.IGNORECASE,
        ),
    ),
    (
        "jwt",
        re.compile(
            r"\beyJ[A-Za-z0-9_\-]{10,}\."
            r"[A-Za-z0-9_\-]{10,}\."
            r"[A-Za-z0-9_\-]{10,}"
        ),
    ),
    (
        "aws_access_key",
        re.compile(
            r"\bAKIA[0-9A-Z]{16}\b"
        ),
    ),
    (
        "private_key_block",
        re.compile(
            r"-----BEGIN [A-Z ]*PRIVATE KEY-----"
        ),
    ),
    (
        "credit_card",
        re.compile(
            r"\b(?:\d[ \-]?){13,16}\b"
        ),
    ),
    (
        "aadhaar",
        re.compile(
            r"\b[2-9]\d{3}"
            r"[ \-]?\d{4}"
            r"[ \-]?\d{4}\b"
        ),
    ),
]


# ---------------------------------------------------------------------------
# Prompt-injection patterns
# ---------------------------------------------------------------------------

INJECTION_PATTERNS: List[
    Tuple[str, re.Pattern]
] = [
    (
        "override_instructions",
        re.compile(
            r"\b(?:ignore|disregard|forget|override|"
            r"bypass|skip)\b"
            r"[^.]{0,40}?"
            r"\b(?:instruction|instructions|prompt|prompts|"
            r"rule|rules|guardrail|guardrails|restriction|"
            r"restrictions|authorization|authorisation|"
            r"permission|permissions|policy|policies|"
            r"validation|security|check|checks)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "role_reassignment",
        re.compile(
            r"\byou\s+are\s+now\b"
            r"|\bact\s+as\s+(?:a|an|the)\s+"
            r"(?:admin|administrator|root)\b"
            r"|\bpretend\s+(?:to\s+be|you\s+are)\b"
            r"|\bfrom\s+now\s+on\s+you\b",
            re.IGNORECASE,
        ),
    ),
    (
        "system_prompt_probe",
        re.compile(
            r"\b(?:show|reveal|print|repeat|output|"
            r"display|tell\s+me)\b"
            r"[^.]{0,30}"
            r"\b(?:system\s+prompt|your\s+prompt|"
            r"your\s+instructions|initial\s+instructions)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "credential_harvest",
        re.compile(
            r"(?:"
            r"\b(?:show|list|reveal|dump|display|export)\b"
            r"[^.]{0,30}"
            r"|"
            r"\b(?:get|give)\b"
            r"[^.]{0,30}"
            r"\b(?:your|my|all|the)\s+"
            r")"
            r"(?:password|passwords|credential|credentials|"
            r"secret|secrets|token|tokens|hash|hashes)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "developer_mode",
        re.compile(
            r"\b(?:developer\s+mode|debug\s+mode|"
            r"god\s+mode|jailbreak|unrestricted\s+mode|"
            r"dan\s+mode)\b",
            re.IGNORECASE,
        ),
    ),
]


# ---------------------------------------------------------------------------
# Bulk-user patterns
# ---------------------------------------------------------------------------

BULK_PATTERNS: List[
    Tuple[str, re.Pattern]
] = [
    (
        "all_users",
        re.compile(
            r"\b(?:all|every|each)\s+"
            r"(?:the\s+)?"
            r"(?:user|users|employee|employees|account|"
            r"accounts|staff|member|members|people)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "list_department",
        re.compile(
            r"\b(?:list|show|get|dump|export|fetch)\b"
            r"[^.]{0,30}"
            r"\b(?:everyone|everybody|entire|whole)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "bulk_department",
        re.compile(
            r"\b(?:users|employees|people|members)\s+"
            r"in\s+(?:the\s+)?\w+\s*"
            r"(?:department|team|division|org|"
            r"organisation|organization)\b",
            re.IGNORECASE,
        ),
    ),
]


_MULTI_USER_SEPARATOR = re.compile(
    r"\band\b|\bplus\b|&|,|;",
    re.IGNORECASE,
)

_NAME_STOPWORDS = {
    "details",
    "detail",
    "password",
    "passwords",
    "account",
    "accounts",
    "status",
    "information",
    "info",
    "profile",
    "profiles",
    "record",
    "records",
    "me",
    "my",
    "him",
    "her",
    "them",
    "it",
    "this",
    "that",
    "please",
    "user",
    "users",
    "employee",
    "employees",
    "everyone",
    "department",
    "team",
    "manager",
    "reset",
    "unlock",
    "access",
}


def _luhn_valid(
    digits: str,
) -> bool:
    """
    Validate a possible credit-card number with the Luhn checksum.

    This prevents ordinary long ticket numbers from being incorrectly
    classified as payment-card data.
    """
    numbers = [
        int(character)
        for character in digits
        if character.isdigit()
    ]

    if len(numbers) < 13:
        return False

    checksum = 0
    parity = len(numbers) % 2

    for index, digit in enumerate(numbers):
        if index % 2 == parity:
            digit *= 2

            if digit > 9:
                digit -= 9

        checksum += digit

    return checksum % 10 == 0


def check_secrets(
    user_input: str,
) -> GuardrailDecision:
    """
    Detect secrets and protected personal identifiers in the query.

    The matched value is never included in logs.
    """
    for label, pattern in SECRET_PATTERNS:
        match = pattern.search(user_input)

        if not match:
            continue

        if (
            label == "credit_card"
            and not _luhn_valid(
                match.group(0)
            )
        ):
            continue

        return block(
            code=ViolationCode.SECRET_IN_INPUT,
            rule=(
                "Input Guardrails - "
                "Sensitive Data Detection"
            ),
            message=(
                "Your request appears to contain sensitive "
                "information such as a password, key or personal "
                "identifier. Please resend it without those details."
            ),
            detail=(
                f"Matched sensitive pattern: {label}"
            ),
        )

    return allow()


def check_prompt_injection(
    user_input: str,
) -> GuardrailDecision:
    """Detect attempts to override system behavior."""
    for label, pattern in INJECTION_PATTERNS:
        if pattern.search(user_input):
            return block(
                code=ViolationCode.PROMPT_INJECTION,
                rule="Prompt Injection Protection",
                message=MSG_NOT_SUPPORTED,
                detail=(
                    f"Matched injection pattern: {label}"
                ),
            )

    return allow()


def check_forbidden_operations(
    user_input: str,
) -> GuardrailDecision:
    """Block explicitly forbidden operations in the raw query."""
    for pattern in FORBIDDEN_OPERATION_PATTERNS:
        if re.search(
            pattern,
            user_input,
            re.IGNORECASE,
        ):
            return block(
                code=ViolationCode.INTENT_NOT_ALLOWED,
                rule="Query Scope Validation",
                message=MSG_NOT_SUPPORTED,
                detail=(
                    "Matched forbidden operation pattern: "
                    f"{pattern}"
                ),
            )

    return allow()


def check_bulk_enumeration(
    user_input: str,
) -> GuardrailDecision:
    """Block requests that ask for several directory users."""
    for label, pattern in BULK_PATTERNS:
        if pattern.search(user_input):
            return block(
                code=ViolationCode.BULK_ENUMERATION,
                rule="No Bulk Enumeration",
                message=MSG_SINGLE_USER,
                detail=(
                    "Matched bulk enumeration pattern: "
                    f"{label}"
                ),
            )

    return allow()


def check_identifier_format(
    user_input: str,
) -> GuardrailDecision:
    """
    Validate email-like tokens before extraction.

    This detects malformed values such as:
        user@
        @coforge.com
        user@@coforge.com

    It does not require an email. The password-reset-specific email
    requirement is applied after intent extraction by engine.py.
    """
    for token in user_input.split():
        candidate = token.strip(
            ".,;:!?\"'()[]<>"
        )

        if "@" not in candidate:
            continue

        if not EMAIL_PATTERN.fullmatch(candidate):
            return block(
                code=ViolationCode.INVALID_IDENTIFIER,
                rule="Input Format Validation",
                message=MSG_INVALID_INPUT,
                detail=(
                    "Malformed email-like token in query"
                ),
            )

    return allow()


def _target_segment(
    text: str,
) -> str:
    """
    Return the query segment that probably names the target user.
    """
    match = re.search(
        r"\bfor\b",
        text,
        re.IGNORECASE,
    )

    if match:
        return text[match.end():].strip()

    return _strip_leading_verb(text).strip()


def _looks_like_a_name(
    segment: str,
) -> bool:
    """Determine whether a separated query segment resembles one username."""
    cleaned = (
        segment.strip()
        .strip(".,;:!?")
        .strip()
    )

    cleaned = re.sub(
        r"^(?:the\s+)?users?\s+",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )

    if not cleaned or " " in cleaned:
        return False

    if cleaned.casefold() in _NAME_STOPWORDS:
        return False

    return bool(
        re.fullmatch(
            r"[A-Za-z]"
            r"[A-Za-z0-9._\-]*"
            r"(?:@[A-Za-z0-9.\-]+)?",
            cleaned,
        )
    )


def check_single_user(
    user_input: str,
) -> GuardrailDecision:
    """
    Require one target user.

    Employee-ID wording does not count as a second user. For example:

        Reset password for user@coforge.com with employee ID 123456

    contains one email and one verification attribute for the same user.
    """
    emails = {
        match.casefold()
        for match in EMAIL_PATTERN.findall(
            user_input
        )
    }

    if len(emails) > 1:
        return block(
            code=ViolationCode.MULTIPLE_USERS,
            rule="Single User Validation",
            message=MSG_SINGLE_USER,
            detail=(
                f"Query contained {len(emails)} "
                "distinct email addresses"
            ),
        )

    target = _target_segment(user_input)

    segments = [
        part
        for part in _MULTI_USER_SEPARATOR.split(
            target
        )
        if part.strip()
    ]

    names = [
        part
        for part in segments
        if _looks_like_a_name(part)
    ]

    if len(names) > 1:
        return block(
            code=ViolationCode.MULTIPLE_USERS,
            rule="Single User Validation",
            message=MSG_SINGLE_USER,
            detail=(
                f"Query names {len(names)} users"
            ),
        )

    return allow()


def _strip_leading_verb(
    text: str,
) -> str:
    """Remove common leading request verbs."""
    return re.sub(
        r"^\s*"
        r"(?:please\s+)?"
        r"(?:can\s+you\s+)?"
        r"(?:get|show|find|fetch|reset|give|list|"
        r"lookup|look\s+up)\s+",
        "",
        text,
        flags=re.IGNORECASE,
    )


def is_allowed_email(
    value: str,
) -> bool:
    """
    Return True when the value is a complete email in an allowed domain.
    """
    if not value:
        return False

    candidate = (
        value.strip()
        .strip("<>\"'")
    )

    if not EMAIL_PATTERN.fullmatch(candidate):
        return False

    if not ALLOWED_EMAIL_DOMAINS:
        return True

    domain = candidate.rsplit(
        "@",
        maxsplit=1,
    )[-1].casefold()

    normalized_domains = {
        str(item).strip().casefold()
        for item in ALLOWED_EMAIL_DOMAINS
        if str(item).strip()
    }

    return domain in normalized_domains


def check_full_email_present(
    user_input: str,
) -> GuardrailDecision:
    """
    Check whether raw input contains a complete allowed email.

    This function is retained for compatibility, but is intentionally not
    called by run_input_checks(). Raw validation does not yet know the intent.

    engine.py uses check_extracted_email() after extraction for password_reset.
    """
    if not REQUIRE_FULL_EMAIL:
        return allow()

    addresses = EMAIL_PATTERN.findall(
        user_input or ""
    )

    if not addresses:
        return block(
            code=ViolationCode.INVALID_IDENTIFIER,
            rule="Full Email Address Required",
            message=MSG_FULL_EMAIL_REQUIRED,
            detail=(
                "No complete email address found "
                "in the query"
            ),
        )

    if (
        ALLOWED_EMAIL_DOMAINS
        and not any(
            is_allowed_email(address)
            for address in addresses
        )
    ):
        return block(
            code=ViolationCode.INVALID_IDENTIFIER,
            rule="Full Email Address Required",
            message=MSG_DOMAIN_NOT_ALLOWED,
            detail=(
                "No email address in an allowed "
                "domain was found"
            ),
        )

    return allow()


def check_extracted_email(
    email: str = None,
) -> GuardrailDecision:
    """
    Validate a complete extracted email.

    engine.py applies this check specifically to password_reset, so Get User
    Details and the other existing Identity operations are not interrupted.
    """
    if not REQUIRE_FULL_EMAIL:
        return allow()

    if not email or not str(email).strip():
        return block(
            code=ViolationCode.INVALID_IDENTIFIER,
            rule="Full Email Address Required",
            message=MSG_FULL_EMAIL_REQUIRED,
            detail=(
                "No email address was extracted "
                "from the password-reset request"
            ),
        )

    if not is_allowed_email(str(email)):
        return block(
            code=ViolationCode.INVALID_IDENTIFIER,
            rule="Full Email Address Required",
            message=MSG_DOMAIN_NOT_ALLOWED,
            detail=(
                "Extracted email is malformed or "
                "outside the allowed domains"
            ),
        )

    return allow()


def validate_identifier(
    email: str = None,
    username: str = None,
    employee_number: str = None,
) -> GuardrailDecision:
    """
    Validate identifiers extracted into structured metadata.
    """
    if (
        email
        and not EMAIL_PATTERN.fullmatch(
            email.strip()
        )
    ):
        return block(
            code=ViolationCode.INVALID_IDENTIFIER,
            rule="Input Format Validation",
            message=MSG_INVALID_INPUT,
            detail="Email failed format validation",
        )

    if (
        username
        and not USERNAME_PATTERN.fullmatch(
            username.strip()
        )
    ):
        if _MULTI_USER_SEPARATOR.search(
            username
        ):
            return block(
                code=ViolationCode.MULTIPLE_USERS,
                rule="Single User Validation",
                message=MSG_SINGLE_USER,
                detail=(
                    "Extracted username contains "
                    "multiple-user separators"
                ),
            )

        return block(
            code=ViolationCode.INVALID_IDENTIFIER,
            rule="Input Format Validation",
            message=MSG_INVALID_INPUT,
            detail=(
                "Username failed format validation"
            ),
        )

    if (
        employee_number
        and not EMPLOYEE_ID_PATTERN.fullmatch(
            str(employee_number).strip()
        )
    ):
        return block(
            code=ViolationCode.INVALID_IDENTIFIER,
            rule="Input Format Validation",
            message=MSG_INVALID_INPUT,
            detail=(
                "Employee ID failed format validation"
            ),
        )

    return allow()


def run_input_checks(
    user_input: str,
) -> GuardrailDecision:
    """
    Run intent-independent raw-input checks.

    Complete email is intentionally not required here. The intent is unknown
    at this stage. Requiring email here would interrupt account unlock, group
    access, create-group, VM, and other supported operations.

    Password-reset-specific email and employee-ID requirements are enforced
    after extraction in GuardrailEngine.validate_request().
    """
    checks = (
        check_secrets,
        check_prompt_injection,
        check_forbidden_operations,
        check_bulk_enumeration,
        check_identifier_format,
        check_single_user,
    )

    for check in checks:
        decision = check(user_input)

        if decision.blocked:
            violation = (
                decision.violations[0]
                if decision.violations
                else None
            )

            logger.warning(
                "GUARDRAIL_INPUT_BLOCKED | "
                "rule={} | code={} | detail={}",
                (
                    violation.rule
                    if violation
                    else "unknown"
                ),
                (
                    violation.code.value
                    if violation
                    else "unknown"
                ),
                (
                    violation.detail
                    if violation
                    else "unknown"
                ),
            )

            return decision

    return allow()