"""
Input Guardrails
Author: Amit Bhagat
Purpose: Checks that run on the raw user query, before the LLM sees it.

Covers sections 1.2, 1.3, 1.4 and the input half of section 1 of the guardrails
design document:

  - secrets and personal data in the query
  - prompt injection attempts
  - identifier format validation, on the raw text and again after extraction
  - single target user
  - bulk enumeration attempts
  - forbidden operations

These run before extraction on purpose. A prompt injection that reaches the
extractor has already had its chance to influence the model, and a password
pasted into a query is already in the model's context and in the logs.
"""

from __future__ import annotations

import re
from typing import List, Tuple

from loguru import logger

from App.guardrails.policy import (
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
EMAIL_PATTERN = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")

# A valid AD username: letters, digits, dot, underscore, hyphen. No spaces, no
# consecutive dots, must start and end alphanumeric.
USERNAME_PATTERN = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9._\-]{0,62}[A-Za-z0-9])?$")

EMPLOYEE_ID_PATTERN = re.compile(r"^[A-Za-z0-9\-]{2,32}$")

# Secrets and personal identifiers that should never be typed into a query.
# Each entry is (label, pattern). The label goes to the audit log; the matched
# text never does.
SECRET_PATTERNS: List[Tuple[str, re.Pattern]] = [
    ("password_assignment", re.compile(
        r"(?:password|passwd|pwd)\s*(?:is|=|:)\s*\S{4,}", re.IGNORECASE)),
    ("api_key", re.compile(
        r"(?:api[_\-\s]?key|apikey)\s*(?:is|=|:)?\s*[A-Za-z0-9_\-]{16,}", re.IGNORECASE)),
    ("bearer_token", re.compile(r"\bBearer\s+[A-Za-z0-9._\-]{20,}", re.IGNORECASE)),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}")),
    ("aws_access_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("private_key_block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    # 13-16 digits, optionally separated. Luhn-checked below to cut false
    # positives from ticket numbers and phone numbers.
    ("credit_card", re.compile(r"\b(?:\d[ \-]?){13,16}\b")),
    # Aadhaar: 12 digits in 4-4-4 grouping, not starting 0 or 1.
    ("aadhaar", re.compile(r"\b[2-9]\d{3}[ \-]?\d{4}[ \-]?\d{4}\b")),
]

# Phrases that try to override system behaviour. Matched case-insensitively
# against the whole query.
INJECTION_PATTERNS: List[Tuple[str, re.Pattern]] = [
    # The filler between the verb and the noun is optional, so both
    # "Ignore previous instructions" and "Forget authorization" match.
    ("override_instructions", re.compile(
        r"\b(?:ignore|disregard|forget|override|bypass|skip)\b[^.]{0,40}?"
        r"\b(?:instruction|instructions|prompt|prompts|rule|rules|"
        r"guardrail|guardrails|restriction|restrictions|authorization|"
        r"authorisation|permission|permissions|policy|policies|"
        r"validation|security|check|checks)\b", re.IGNORECASE)),
    ("role_reassignment", re.compile(
        r"\byou\s+are\s+now\b|\bact\s+as\s+(?:a|an|the)\s+(?:admin|administrator|root)\b|"
        r"\bpretend\s+(?:to\s+be|you\s+are)\b|\bfrom\s+now\s+on\s+you\b", re.IGNORECASE)),
    ("system_prompt_probe", re.compile(
        r"\b(?:show|reveal|print|repeat|output|display|tell\s+me)\b[^.]{0,30}"
        r"\b(?:system\s+prompt|your\s+prompt|your\s+instructions|initial\s+instructions)\b",
        re.IGNORECASE)),
    ("credential_harvest", re.compile(
        r"\b(?:show|list|reveal|get|give|dump|display|export)\b[^.]{0,30}"
        r"\b(?:all\s+)?(?:password|passwords|credential|credentials|"
        r"secret|secrets|token|tokens|hash|hashes)\b", re.IGNORECASE)),
    ("developer_mode", re.compile(
        r"\b(?:developer\s+mode|debug\s+mode|god\s+mode|jailbreak|"
        r"unrestricted\s+mode|dan\s+mode)\b", re.IGNORECASE)),
]

# Requests for many users at once.
BULK_PATTERNS: List[Tuple[str, re.Pattern]] = [
    ("all_users", re.compile(
        r"\b(?:all|every|each)\s+(?:the\s+)?(?:user|users|employee|employees|"
        r"account|accounts|staff|member|members|people)\b", re.IGNORECASE)),
    ("list_department", re.compile(
        r"\b(?:list|show|get|dump|export|fetch)\b[^.]{0,30}"
        r"\b(?:everyone|everybody|entire|whole)\b", re.IGNORECASE)),
    ("bulk_department", re.compile(
        r"\b(?:users|employees|people|members)\s+in\s+(?:the\s+)?\w+\s*"
        r"(?:department|team|division|org|organisation|organization)\b", re.IGNORECASE)),
]

# Words that join several names together, used by the single-user check.
_MULTI_USER_SEPARATOR = re.compile(r"\band\b|\bplus\b|&|,|;", re.IGNORECASE)

# Single words that can sit where a name would but are not names.
_NAME_STOPWORDS = {
    "details", "detail", "password", "passwords", "account", "accounts",
    "status", "information", "info", "profile", "profiles", "record",
    "records", "me", "my", "him", "her", "them", "it", "this", "that",
    "please", "user", "users", "employee", "employees", "everyone",
    "department", "team", "manager", "reset", "unlock", "access",
}


def _luhn_valid(digits: str) -> bool:
    """
    Luhn checksum, used to confirm a digit run is really a card number.

    Without this, any 13-to-16 digit sequence (a ticket ID, a phone number with
    an extension) trips the credit card rule and blocks a legitimate request.
    """
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


def check_secrets(user_input: str) -> GuardrailDecision:
    """
    Detect secrets and personal identifiers pasted into the query.

    Section 1 of the design document: passwords, API keys, access tokens,
    credit card numbers, Aadhaar numbers, personal information.

    The matched value is never logged, only the label of the pattern that hit.
    Logging the match would put the secret straight into the log file the
    guardrail exists to keep it out of.

    Args:
        user_input: The raw user query.

    Returns:
        A GuardrailDecision. Blocks when a secret is found.
    """
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
                "Your request appears to contain sensitive information such as a "
                "password, key or personal identifier. Please resend it without "
                "those details."
            ),
            detail=f"Matched sensitive pattern: {label}",
        )

    return allow()


def check_prompt_injection(user_input: str) -> GuardrailDecision:
    """
    Detect attempts to override system instructions.

    Section 1.4. The user-facing message stays generic so a probe does not learn
    which phrasing tripped the check.

    Args:
        user_input: The raw user query.

    Returns:
        A GuardrailDecision. Blocks on a match.
    """
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
    """
    Catch explicitly forbidden operations in the raw query.

    Section 1.1. The intent allowlist already refuses anything unsupported, but
    matching here means "Delete all users" is logged as an attempted forbidden
    operation rather than as an unrecognised intent.

    Args:
        user_input: The raw user query.

    Returns:
        A GuardrailDecision. Blocks on a match.
    """
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
    """
    Block requests that ask for many users at once.

    Section 2.3. Catches "get details of all employees" and "list every user in
    Finance" before they reach a tool.

    Args:
        user_input: The raw user query.

    Returns:
        A GuardrailDecision. Blocks on a match.
    """
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
    """
    Validate identifier formats in the raw query, before extraction.

    Section 1.3. The design document's own example is "amit@@@", which is
    malformed in a way no amount of model reasoning can fix, so there is no
    reason to spend an LLM call discovering that.

    The rule: any whitespace-separated token containing "@" must be a complete,
    well-formed email address. That catches amit@@@, amit.bhagat@@@coforge.com,
    user@, @coforge.com and trailing-dot variants, while leaving tokens with no
    "@" alone for the extractor to interpret.

    Args:
        user_input: The raw user query.

    Returns:
        A GuardrailDecision. Blocks on a malformed identifier.
    """
    for token in user_input.split():
        # Trailing sentence punctuation is not part of the address.
        candidate = token.strip(".,;:!?\"'()[]<>")

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
    """
    Return the part of the query that names the target user.

    Everything after the first "for" is the target in almost every phrasing the
    system sees. Isolating it matters because "and" is common in ordinary
    request wording: "get details and account status for amit.bhagat" joins two
    *fields*, not two people, and only the part after "for" should be counted.

    Falls back to the whole query with the leading command verb removed, for
    phrasings that have no "for" at all.
    """
    match = re.search(r"\bfor\b", text, re.IGNORECASE)
    if match:
        return text[match.end():].strip()
    return _strip_leading_verb(text).strip()


def _looks_like_a_name(segment: str) -> bool:
    """
    Decide whether one comma or "and" separated segment names a person.

    A name is a single token: amit, amit.bhagat, amit.bhagat@coforge.com. A
    multi-word phrase such as "the finance team" is not, which keeps ordinary
    prose from being counted as a list of people.
    """
    cleaned = segment.strip().strip(".,;:!?").strip()

    # Drop a leading "user" or "users", so "user amit" still reads as one name.
    cleaned = re.sub(r"^(?:the\s+)?users?\s+", "", cleaned, flags=re.IGNORECASE)

    if not cleaned or " " in cleaned:
        return False

    if cleaned.lower() in _NAME_STOPWORDS:
        return False

    return bool(re.fullmatch(r"[A-Za-z][A-Za-z0-9._\-]*(?:@[A-Za-z0-9.\-]+)?", cleaned))


def check_single_user(user_input: str) -> GuardrailDecision:
    """
    Require exactly one target user in the request.

    Section 1.2. Two independent signals:

      - more than one distinct email address anywhere in the query
      - more than one name-like segment after "for", once the query is split on
        commas, "and" and ampersands

    The second signal is case-insensitive by design. An earlier version keyed on
    capitalised words, which caught "Amit, Ravi and Aman" but let
    "aman, ravi and amit" through; people type lowercase far more often than not.

    Args:
        user_input: The raw user query.

    Returns:
        A GuardrailDecision. Blocks when more than one target is present.
    """
    emails = {match.lower() for match in EMAIL_PATTERN.findall(user_input)}

    if len(emails) > 1:
        return block(
            code=ViolationCode.MULTIPLE_USERS,
            rule="Single User Validation",
            message=MSG_SINGLE_USER,
            detail=f"Query contained {len(emails)} distinct email addresses",
        )

    target = _target_segment(user_input)
    segments = [part for part in _MULTI_USER_SEPARATOR.split(target) if part.strip()]
    names = [part for part in segments if _looks_like_a_name(part)]

    if len(names) > 1:
        return block(
            code=ViolationCode.MULTIPLE_USERS,
            rule="Single User Validation",
            message=MSG_SINGLE_USER,
            detail=f"Query names {len(names)} users: {len(names)} name-like segments",
        )

    return allow()


def _strip_leading_verb(text: str) -> str:
    """
    Remove the leading command words before scanning for names.

    "Get details for Amit and Ravi" starts with capitalised words that are not
    names. Dropping the first few tokens keeps them out of the count.
    """
    return re.sub(
        r"^\s*(?:please\s+)?(?:can\s+you\s+)?(?:get|show|find|fetch|reset|"
        r"give|list|lookup|look\s+up)\s+",
        "",
        text,
        flags=re.IGNORECASE,
    )


def validate_identifier(
    email: str = None,
    username: str = None,
    employee_number: str = None,
) -> GuardrailDecision:
    """
    Validate the format of whichever identifiers were extracted.

    Section 1.3. Runs after extraction, on the structured metadata rather than
    the raw text, so it checks the value that will actually be sent to Graph.

    Args:
        email: Extracted email address, if any.
        username: Extracted username, if any.
        employee_number: Extracted employee number, if any.

    Returns:
        A GuardrailDecision. Blocks on a malformed value.
    """
    if email and not EMAIL_PATTERN.fullmatch(email.strip()):
        return block(
            code=ViolationCode.INVALID_IDENTIFIER,
            rule="Input Format Validation",
            message=MSG_INVALID_INPUT,
            detail="Email failed format validation",
        )

    if username and not USERNAME_PATTERN.fullmatch(username.strip()):
        # A username carrying separators is a list of people that the input
        # check did not catch, not a malformed single name. Reporting it as a
        # format error sends the user off to fix their spelling when the real
        # problem is that they asked for three accounts at once.
        if _MULTI_USER_SEPARATOR.search(username):
            return block(
                code=ViolationCode.MULTIPLE_USERS,
                rule="Single User Validation",
                message=MSG_SINGLE_USER,
                detail=f"Extracted username contains separators: {username!r}",
            )

        return block(
            code=ViolationCode.INVALID_IDENTIFIER,
            rule="Input Format Validation",
            message=MSG_INVALID_INPUT,
            detail="Username failed format validation",
        )

    if employee_number and not EMPLOYEE_ID_PATTERN.fullmatch(str(employee_number).strip()):
        return block(
            code=ViolationCode.INVALID_IDENTIFIER,
            rule="Input Format Validation",
            message=MSG_INVALID_INPUT,
            detail="Employee number failed format validation",
        )

    return allow()


def run_input_checks(user_input: str) -> GuardrailDecision:
    """
    Run every raw-input check, in order, stopping at the first block.

    Order matters. Secrets are checked first so a pasted password is caught even
    if the query would fail a later check anyway, which keeps it out of the
    extractor's context either way.

    Args:
        user_input: The raw user query.

    Returns:
        The first blocking decision, or allow() if everything passed.
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
            logger.warning(
                "GUARDRAIL_INPUT_BLOCKED | rule={} | code={} | detail={}",
                decision.violations[0].rule,
                decision.violations[0].code.value,
                decision.violations[0].detail,
            )
            return decision

    return allow()
