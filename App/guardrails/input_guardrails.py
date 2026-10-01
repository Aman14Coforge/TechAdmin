"""
Input Guardrails
Author: Amit Bhagat
Purpose: Checks that run on the raw user query, before the LLM sees it.

Preserves all existing user-operation protections and adds read-only Active
Directory computer lookup support. Computer-detail requests may use one valid
computer identifier instead of a user email address.
"""

from __future__ import annotations

import re
from typing import List, Tuple

from loguru import logger

from App.guardrails.policy import (
    ALLOWED_EMAIL_DOMAINS,
    MSG_DOMAIN_NOT_ALLOWED,
    MSG_FULL_EMAIL_REQUIRED,
    REQUIRE_FULL_EMAIL,
    FORBIDDEN_OPERATION_PATTERNS,
    MSG_INVALID_INPUT,
    MSG_NOT_SUPPORTED,
    MSG_SINGLE_USER,
)
from App.guardrails.schemas import (
    GuardrailDecision,
    ViolationCode,
    allow,
    block,
)


# ---------------------------------------------------------------------------
# Patterns
# ---------------------------------------------------------------------------

EMAIL_PATTERN = re.compile(
    r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}"
)

# A valid AD username: letters, digits, dot, underscore, hyphen. No spaces,
# starts and ends with an alphanumeric character.
USERNAME_PATTERN = re.compile(
    r"^[A-Za-z0-9](?:[A-Za-z0-9._\-]{0,62}[A-Za-z0-9])?$"
)

EMPLOYEE_ID_PATTERN = re.compile(r"^[A-Za-z0-9\-]{2,32}$")

# One conservative AD computer identifier. This accepts a short hostname,
# DNS hostname, or computer SAM account ending in $. To avoid treating a bare
# username or ordinary word as a computer, the identifier must contain either:
#   - a hyphen plus at least one digit, or
#   - a DNS dot plus at least one digit, or
#   - the trailing computer-account marker $.
COMPUTER_IDENTIFIER_PATTERN = re.compile(
    r"^(?=.{2,253}$)(?!.*\.\.)"
    r"(?=[A-Za-z0-9._$\-]*[A-Za-z])"
    r"(?:"
    r"(?=[A-Za-z0-9._\-]*\d)(?=[A-Za-z0-9._\-]*[-.])"
    r"[A-Za-z0-9](?:[A-Za-z0-9._\-]*[A-Za-z0-9])?"
    r"|"
    r"[A-Za-z0-9](?:[A-Za-z0-9._\-]*[A-Za-z0-9])?\$"
    r")$",
    re.IGNORECASE,
)

# Context words strengthen detection for less distinctive hostnames. The
# identifier-only case LP-TZD-81007633 is already accepted by the conservative
# computer identifier pattern.
COMPUTER_CONTEXT_PATTERN = re.compile(
    r"\b(?:ad\s+computer|computer(?:\s+account)?|workstation|machine|device|"
    r"server|hostname|host|laptop|desktop)\b",
    re.IGNORECASE,
)

# Tokens that can occur around a hostname but are never computer identifiers.
_COMPUTER_STOPWORDS = {
    "a", "active", "ad", "and", "computer", "details", "detail", "device",
    "directory", "for", "get", "give", "host", "hostname", "information",
    "laptop", "lookup", "machine", "me", "of", "please", "record", "server",
    "show", "the", "this", "workstation",
}

SECRET_PATTERNS: List[Tuple[str, re.Pattern]] = [
    (
        "password_assignment",
        re.compile(
            r"(?:password|passwd|pwd)\s*(?:is|=|:)\s*\S{4,}",
            re.IGNORECASE,
        ),
    ),
    (
        "api_key",
        re.compile(
            r"(?:api[_\-\s]?key|apikey)\s*(?:is|=|:)?\s*"
            r"[A-Za-z0-9_\-]{16,}",
            re.IGNORECASE,
        ),
    ),
    (
        "bearer_token",
        re.compile(r"\bBearer\s+[A-Za-z0-9._\-]{20,}", re.IGNORECASE),
    ),
    (
        "jwt",
        re.compile(
            r"\beyJ[A-Za-z0-9_\-]{10,}\."
            r"[A-Za-z0-9_\-]{10,}\."
            r"[A-Za-z0-9_\-]{10,}"
        ),
    ),
    ("aws_access_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    (
        "private_key_block",
        re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    ),
    ("credit_card", re.compile(r"\b(?:\d[ \-]?){13,16}\b")),
    ("aadhaar", re.compile(r"\b[2-9]\d{3}[ \-]?\d{4}[ \-]?\d{4}\b")),
]

INJECTION_PATTERNS: List[Tuple[str, re.Pattern]] = [
    (
        "override_instructions",
        re.compile(
            r"\b(?:ignore|disregard|forget|override|bypass|skip)\b"
            r"[^.]{0,40}?\b(?:instruction|instructions|prompt|prompts|rule|"
            r"rules|guardrail|guardrails|restriction|restrictions|authorization|"
            r"authorisation|permission|permissions|policy|policies|validation|"
            r"security|check|checks)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "role_reassignment",
        re.compile(
            r"\byou\s+are\s+now\b|"
            r"\bact\s+as\s+(?:a|an|the)\s+(?:admin|administrator|root)\b|"
            r"\bpretend\s+(?:to\s+be|you\s+are)\b|"
            r"\bfrom\s+now\s+on\s+you\b",
            re.IGNORECASE,
        ),
    ),
    (
        "system_prompt_probe",
        re.compile(
            r"\b(?:show|reveal|print|repeat|output|display|tell\s+me)\b"
            r"[^.]{0,30}\b(?:system\s+prompt|your\s+prompt|your\s+instructions|"
            r"initial\s+instructions)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "credential_harvest",
        re.compile(
            r"(?:\b(?:show|list|reveal|dump|display|export)\b[^.]{0,30}|"
            r"\b(?:get|give)\b[^.]{0,30}\b(?:your|my|all|the)\s+)"
            r"(?:password|passwords|credential|credentials|secret|secrets|"
            r"token|tokens|hash|hashes)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "developer_mode",
        re.compile(
            r"\b(?:developer\s+mode|debug\s+mode|god\s+mode|jailbreak|"
            r"unrestricted\s+mode|dan\s+mode)\b",
            re.IGNORECASE,
        ),
    ),
]

BULK_PATTERNS: List[Tuple[str, re.Pattern]] = [
    (
        "all_users",
        re.compile(
            r"\b(?:all|every|each)\s+(?:the\s+)?(?:user|users|employee|"
            r"employees|account|accounts|staff|member|members|people)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "list_department",
        re.compile(
            r"\b(?:list|show|get|dump|export|fetch)\b[^.]{0,30}"
            r"\b(?:everyone|everybody|entire|whole)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "bulk_department",
        re.compile(
            r"\b(?:users|employees|people|members)\s+in\s+(?:the\s+)?\w+\s*"
            r"(?:department|team|division|org|organisation|organization)\b",
            re.IGNORECASE,
        ),
    ),
]

_MULTI_USER_SEPARATOR = re.compile(r"\band\b|\bplus\b|&|,|;", re.IGNORECASE)

_NAME_STOPWORDS = {
    "details", "detail", "password", "passwords", "account", "accounts",
    "status", "information", "info", "profile", "profiles", "record",
    "records", "me", "my", "him", "her", "them", "it", "this", "that",
    "please", "user", "users", "employee", "employees", "everyone",
    "department", "team", "manager", "reset", "unlock", "access",
}


# ---------------------------------------------------------------------------
# General helpers
# ---------------------------------------------------------------------------


def _luhn_valid(digits: str) -> bool:
    numbers = [int(char) for char in digits if char.isdigit()]
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


def _clean_query_token(token: str) -> str:
    return token.strip(".,;:!?\"'()[]<>{}")


def is_valid_computer_identifier(value: str | None) -> bool:
    """Return True for one conservative AD computer identifier."""

    if not value:
        return False

    candidate = _clean_query_token(str(value).strip())
    if not candidate or "@" in candidate:
        return False

    if candidate.casefold() in _COMPUTER_STOPWORDS:
        return False

    return COMPUTER_IDENTIFIER_PATTERN.fullmatch(candidate) is not None


def extract_computer_identifier(user_input: str) -> str | None:
    """
    Extract one computer identifier from the raw query.

    A hostname with a hyphen/dot plus digits, such as LP-TZD-81007633, can be
    recognized without an explicit computer keyword. Less distinctive values
    are accepted only when the query contains computer context.
    """

    if not isinstance(user_input, str) or not user_input.strip():
        return None

    candidates: list[str] = []

    for raw_token in user_input.split():
        candidate = _clean_query_token(raw_token)
        if is_valid_computer_identifier(candidate):
            candidates.append(candidate)

    unique_candidates = list(dict.fromkeys(candidates))

    if len(unique_candidates) == 1:
        return unique_candidates[0]

    if len(unique_candidates) > 1:
        return None

    if COMPUTER_CONTEXT_PATTERN.search(user_input) is None:
        return None

    # Contextual fallback for clean short hostnames that do not contain digits.
    target = _target_segment(user_input)
    contextual_tokens = [
        _clean_query_token(token)
        for token in target.split()
    ]

    valid_contextual = []
    for candidate in contextual_tokens:
        if not candidate or "@" in candidate:
            continue
        if candidate.casefold() in _COMPUTER_STOPWORDS:
            continue
        if USERNAME_PATTERN.fullmatch(candidate):
            valid_contextual.append(candidate)

    unique_contextual = list(dict.fromkeys(valid_contextual))
    return unique_contextual[0] if len(unique_contextual) == 1 else None


def is_computer_lookup_request(user_input: str) -> bool:
    """Return True when the raw query contains exactly one computer target."""

    return extract_computer_identifier(user_input) is not None


# ---------------------------------------------------------------------------
# Raw-input checks
# ---------------------------------------------------------------------------


def check_secrets(user_input: str) -> GuardrailDecision:
    for label, pattern in SECRET_PATTERNS:
        match = pattern.search(user_input)
        if not match:
            continue

        if label == "credit_card" and not _luhn_valid(match.group(0)):
            continue

        return block(
            code=ViolationCode.SECRET_IN_INPUT,
            rule="Input Guardrails - Sensitive Data Detection",
            message=(
                "Your request appears to contain sensitive information such as "
                "a password, key or personal identifier. Please resend it "
                "without those details."
            ),
            detail=f"Matched sensitive pattern: {label}",
        )

    return allow()


def check_prompt_injection(user_input: str) -> GuardrailDecision:
    for label, pattern in INJECTION_PATTERNS:
        if pattern.search(user_input):
            return block(
                code=ViolationCode.PROMPT_INJECTION,
                rule="Prompt Injection Protection",
                message=MSG_NOT_SUPPORTED,
                detail=f"Matched injection pattern: {label}",
            )

    return allow()


def check_forbidden_operations(user_input: str) -> GuardrailDecision:
    for pattern in FORBIDDEN_OPERATION_PATTERNS:
        if re.search(pattern, user_input, re.IGNORECASE):
            return block(
                code=ViolationCode.INTENT_NOT_ALLOWED,
                rule="Query Scope Validation",
                message=MSG_NOT_SUPPORTED,
                detail=f"Matched forbidden operation pattern: {pattern}",
            )

    return allow()


def check_bulk_enumeration(user_input: str) -> GuardrailDecision:
    for label, pattern in BULK_PATTERNS:
        if pattern.search(user_input):
            return block(
                code=ViolationCode.BULK_ENUMERATION,
                rule="No Bulk Enumeration",
                message=MSG_SINGLE_USER,
                detail=f"Matched bulk enumeration pattern: {label}",
            )

    return allow()


def check_identifier_format(user_input: str) -> GuardrailDecision:
    for token in user_input.split():
        candidate = _clean_query_token(token)

        if "@" not in candidate:
            continue

        if not EMAIL_PATTERN.fullmatch(candidate):
            return block(
                code=ViolationCode.INVALID_IDENTIFIER,
                rule="Input Format Validation",
                message=MSG_INVALID_INPUT,
                detail=f"Malformed email-like token in query: {candidate!r}",
            )

    return allow()


def _target_segment(text: str) -> str:
    match = re.search(r"\bfor\b", text, re.IGNORECASE)
    if match:
        return text[match.end():].strip()
    return _strip_leading_verb(text).strip()


def _looks_like_a_name(segment: str) -> bool:
    cleaned = segment.strip().strip(".,;:!?").strip()
    cleaned = re.sub(
        r"^(?:the\s+)?users?\s+",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )

    if not cleaned or " " in cleaned:
        return False

    if cleaned.lower() in _NAME_STOPWORDS:
        return False

    return bool(
        re.fullmatch(
            r"[A-Za-z][A-Za-z0-9._\-]*(?:@[A-Za-z0-9.\-]+)?",
            cleaned,
        )
    )


def check_single_user(user_input: str) -> GuardrailDecision:
    emails = {match.lower() for match in EMAIL_PATTERN.findall(user_input)}

    if len(emails) > 1:
        return block(
            code=ViolationCode.MULTIPLE_USERS,
            rule="Single User Validation",
            message=MSG_SINGLE_USER,
            detail=f"Query contained {len(emails)} distinct email addresses",
        )

    target = _target_segment(user_input)
    segments = [
        part
        for part in _MULTI_USER_SEPARATOR.split(target)
        if part.strip()
    ]
    names = [part for part in segments if _looks_like_a_name(part)]

    if len(names) > 1:
        return block(
            code=ViolationCode.MULTIPLE_USERS,
            rule="Single User Validation",
            message=MSG_SINGLE_USER,
            detail=(
                f"Query names {len(names)} users: "
                f"{len(names)} name-like segments"
            ),
        )

    return allow()


def _strip_leading_verb(text: str) -> str:
    return re.sub(
        r"^\s*(?:please\s+)?(?:can\s+you\s+)?(?:get|show|find|fetch|reset|"
        r"give|list|lookup|look\s+up)\s+",
        "",
        text,
        flags=re.IGNORECASE,
    )


# ---------------------------------------------------------------------------
# Full-email requirement, with computer-lookup exception
# ---------------------------------------------------------------------------


def is_allowed_email(value: str) -> bool:
    if not value:
        return False

    candidate = value.strip().strip("<>\"'")

    if not EMAIL_PATTERN.fullmatch(candidate):
        return False

    if not ALLOWED_EMAIL_DOMAINS:
        return True

    domain = candidate.rsplit("@", 1)[-1].lower()
    return domain in ALLOWED_EMAIL_DOMAINS


def check_full_email_present(user_input: str) -> GuardrailDecision:
    """
    Require a complete email for user operations while allowing one validated
    AD computer identifier to reach semantic extraction.
    """

    if not REQUIRE_FULL_EMAIL:
        return allow()

    computer_identifier = extract_computer_identifier(user_input)
    if computer_identifier:
        logger.info(
            "GUARDRAIL_COMPUTER_IDENTIFIER_ACCEPTED | computer_identifier={}",
            computer_identifier,
        )
        return allow()

    addresses = EMAIL_PATTERN.findall(user_input or "")

    if not addresses:
        return block(
            code=ViolationCode.INVALID_IDENTIFIER,
            rule="Full Email Address Required",
            message=MSG_FULL_EMAIL_REQUIRED,
            detail="No complete email address found in the query",
        )

    if ALLOWED_EMAIL_DOMAINS and not any(
        is_allowed_email(address)
        for address in addresses
    ):
        return block(
            code=ViolationCode.INVALID_IDENTIFIER,
            rule="Full Email Address Required",
            message=MSG_DOMAIN_NOT_ALLOWED,
            detail=(
                "No address in an allowed domain "
                f"({sorted(ALLOWED_EMAIL_DOMAINS)}) was found"
            ),
        )

    return allow()


def check_extracted_email(
    email: str = None,
    *,
    intent: str = None,
    hostname: str = None,
) -> GuardrailDecision:
    """
    Require extracted email metadata for user operations.

    For get_computer_details, a valid extracted hostname replaces the email
    requirement. Callers should pass intent and hostname after extraction.
    Existing callers that pass only email continue to enforce the old rule.
    """

    normalized_intent = (
        str(getattr(intent, "value", intent) or "")
        .strip()
        .casefold()
    )

    if normalized_intent == "get_computer_details":
        if is_valid_computer_identifier(hostname):
            return allow()

        return block(
            code=ViolationCode.INVALID_IDENTIFIER,
            rule="Computer Identifier Required",
            message=(
                "Please provide one valid computer name or hostname, "
                "for example LP-TZD-81007633."
            ),
            detail=(
                "get_computer_details was extracted without a valid hostname"
            ),
        )

    if not REQUIRE_FULL_EMAIL:
        return allow()

    if not email or not str(email).strip():
        return block(
            code=ViolationCode.INVALID_IDENTIFIER,
            rule="Full Email Address Required",
            message=MSG_FULL_EMAIL_REQUIRED,
            detail="No email address was extracted from the request",
        )

    if not is_allowed_email(str(email)):
        return block(
            code=ViolationCode.INVALID_IDENTIFIER,
            rule="Full Email Address Required",
            message=MSG_DOMAIN_NOT_ALLOWED,
            detail="Extracted email is malformed or outside the allowed domains",
        )

    return allow()


# ---------------------------------------------------------------------------
# Structured identifier validation
# ---------------------------------------------------------------------------


def validate_identifier(
    email: str = None,
    username: str = None,
    employee_number: str = None,
    hostname: str = None,
    intent: str = None,
) -> GuardrailDecision:
    """
    Validate identifiers after extraction.

    Existing callers remain compatible. For get_computer_details, callers
    should additionally pass hostname and intent.
    """

    normalized_intent = (
        str(getattr(intent, "value", intent) or "")
        .strip()
        .casefold()
    )

    if normalized_intent == "get_computer_details":
        if not is_valid_computer_identifier(hostname):
            return block(
                code=ViolationCode.INVALID_IDENTIFIER,
                rule="Input Format Validation",
                message=(
                    "Please provide one valid computer name or hostname, "
                    "for example LP-TZD-81007633."
                ),
                detail="Computer hostname failed format validation",
            )
        return allow()

    if email and not EMAIL_PATTERN.fullmatch(email.strip()):
        return block(
            code=ViolationCode.INVALID_IDENTIFIER,
            rule="Input Format Validation",
            message=MSG_INVALID_INPUT,
            detail="Email failed format validation",
        )

    if username and not USERNAME_PATTERN.fullmatch(username.strip()):
        if _MULTI_USER_SEPARATOR.search(username):
            return block(
                code=ViolationCode.MULTIPLE_USERS,
                rule="Single User Validation",
                message=MSG_SINGLE_USER,
                detail=(
                    "Extracted username contains separators: "
                    f"{username!r}"
                ),
            )

        return block(
            code=ViolationCode.INVALID_IDENTIFIER,
            rule="Input Format Validation",
            message=MSG_INVALID_INPUT,
            detail="Username failed format validation",
        )

    if employee_number and not EMPLOYEE_ID_PATTERN.fullmatch(
        str(employee_number).strip()
    ):
        return block(
            code=ViolationCode.INVALID_IDENTIFIER,
            rule="Input Format Validation",
            message=MSG_INVALID_INPUT,
            detail="Employee number failed format validation",
        )

    return allow()


# ---------------------------------------------------------------------------
# Guardrail pipeline
# ---------------------------------------------------------------------------


def run_input_checks(user_input: str) -> GuardrailDecision:
    checks = (
        check_secrets,
        check_prompt_injection,
        check_forbidden_operations,
        check_bulk_enumeration,
        check_identifier_format,
        check_single_user,
        check_full_email_present,
    )

    for check in checks:
        decision = check(user_input)
        if decision.blocked:
            logger.warning(
                "GUARDRAIL_INPUT_BLOCKED | rule={} | code={} | detail={}",
                decision.violations[0].rule,
                decision.violations[0].code.value,
                decision.violations[0].detail,
            )
            return decision

    return allow()
