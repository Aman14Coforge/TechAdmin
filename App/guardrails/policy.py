"""
Guardrail Policy
Author: Amit Bhagat
Purpose: Every tunable value the guardrails use, in one place.

These are policy decisions rather than logic, so they live apart from the
checks that read them. Changing who counts as privileged, or which Graph fields
may be returned, should not mean editing control flow.

Values that a deployment will realistically want to change are read from the
environment, with defaults that are safe if nothing is set.
"""

from __future__ import annotations

import os
from typing import Set


def _env_bool(name: str, default: bool) -> bool:
    """Read a boolean environment variable. Accepts true/1/yes/on."""
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"true", "1", "yes", "on"}


def _env_set(name: str, default: str) -> Set[str]:
    """Read a comma-separated environment variable into a lowercase set."""
    raw = os.getenv(name, default)
    return {item.strip().lower() for item in raw.split(",") if item.strip()}


# ---------------------------------------------------------------------------
# 1.1 Query Scope Validation
# ---------------------------------------------------------------------------
# Only these intents may reach a tool. The extractor can produce others, and
# more will be added over time, so this allowlist is what actually decides
# rather than the enum. Anything not listed is refused.
ALLOWED_INTENTS: Set[str] = _env_set(
    "GUARDRAIL_ALLOWED_INTENTS",
    "get_user_details,password_reset",
)

# Operations the system must never perform, listed so an attempt can be logged
# under a clear code rather than a generic refusal.
FORBIDDEN_OPERATION_PATTERNS = [
    r"\bdelete\s+(all\s+)?(user|users|account|accounts)\b",
    r"\bcreate\s+(an?\s+)?(admin|administrator|user|account)\b",
    r"\bshut\s*down\b",
    r"\breboot\s+(the\s+)?server\b",
    r"\bdrop\s+(table|database)\b",
    r"\bdisable\s+(all\s+)?(user|users|account|accounts)\b",
    r"\bgrant\s+(me\s+)?(admin|administrator|global\s+admin)\b",
]


# ---------------------------------------------------------------------------
# 2.1 / 3.1 Authorization
# ---------------------------------------------------------------------------
class Role:
    """The roles the authorization check understands."""

    EMPLOYEE = "employee"
    HELPDESK = "helpdesk"
    ADMIN = "admin"


# Who may run what. Self-lookup is handled separately, so an employee can
# always read their own record even though they are not listed here.
ROLE_PERMISSIONS = {
    Role.EMPLOYEE: {"get_user_details"},
    Role.HELPDESK: {"get_user_details", "password_reset"},
    Role.ADMIN: {"get_user_details", "password_reset"},
}

# The role assumed when the caller does not supply one. Deliberately the least
# privileged: an unauthenticated demo should not be able to reset passwords.
DEFAULT_ROLE = os.getenv("GUARDRAIL_DEFAULT_ROLE", Role.HELPDESK)


# ---------------------------------------------------------------------------
# 3.2 High-Privilege Account Protection
# ---------------------------------------------------------------------------
# Accounts that need a second approval before any modification. Matched on the
# username portion, case-insensitively.
PRIVILEGED_USERNAMES: Set[str] = _env_set(
    "GUARDRAIL_PRIVILEGED_USERNAMES",
    "administrator,admin,root,breakglass,break-glass,emergency",
)

# Substrings that mark an account as privileged. Catches naming conventions
# like svc-backup, globaladmin.reporting or domain.admin.
PRIVILEGED_PATTERNS = [
    "domainadmin",
    "domain.admin",
    "globaladmin",
    "global.admin",
    "svc-",
    "svc.",
    "service.account",
    "serviceaccount",
    "breakglass",
    "break-glass",
    "-admin",
    ".admin",
    "_admin",
]

# Job titles that mark a target as high-privilege. Checked against the Graph
# record before a reset, which catches "Reset CEO password" even when the
# username itself looks ordinary.
PRIVILEGED_JOB_TITLES: Set[str] = _env_set(
    "GUARDRAIL_PRIVILEGED_TITLES",
    "ceo,cto,cfo,coo,chief executive officer,chief technology officer,"
    "chief financial officer,chief operating officer,president,"
    "managing director,domain administrator,global administrator",
)


# ---------------------------------------------------------------------------
# Demo visibility switches
#
# These two relax sections 2.2 and 3.3 so a demo can show what the API actually
# returned. They default to ON because the current demo needs the values on
# screen. Set either to false to restore the behaviour the guardrails design
# document specifies:
#
#     GUARDRAIL_SHOW_ALL_USER_FIELDS=false   # re-enable the field allowlist
#     GUARDRAIL_SHOW_PASSWORD=false          # re-hide the temporary password
#
# Turn both off before anything resembling production. A temporary password on
# screen is a credential in a browser cache, a screenshot and a support
# transcript, and the full Graph record carries fields no requester needs.
# ---------------------------------------------------------------------------
SHOW_ALL_USER_FIELDS = _env_bool("GUARDRAIL_SHOW_ALL_USER_FIELDS", True)
SHOW_TEMPORARY_PASSWORD = _env_bool("GUARDRAIL_SHOW_PASSWORD", True)


# ---------------------------------------------------------------------------
# 2.2 Minimum Data Exposure
# ---------------------------------------------------------------------------
# The only Graph fields that may be returned for a user lookup. An allowlist
# rather than a blocklist, so a field added by Graph in future is withheld by
# default instead of leaking until someone notices.
ALLOWED_USER_FIELDS: Set[str] = {
    "id",
    "displayName",
    "userPrincipalName",
    "mail",
    "department",
    "jobTitle",
    "manager",
    "accountEnabled",
    "userType",
    "officeLocation",
}

# Field names that must never appear in any output, at any nesting depth.
# Matched as substrings, case-insensitively, so passwordHash, password_hash and
# newPassword are all caught by "password".
SENSITIVE_FIELD_MARKERS = [
    "password",
    "passwd",
    "pwd",
    "secret",
    "token",
    "credential",
    "salary",
    "compensation",
    "mfa",
    "securityquestion",
    "security_question",
    "apikey",
    "api_key",
    "privatekey",
    "private_key",
    "ssn",
    "aadhaar",
    "creditcard",
    "credit_card",
    "homeaddress",
    "home_address",
    "streetaddress",
    "street_address",
    "mobilephone",
    "personal_email",
]


# Markers that stay redacted even when the demo switches are on. Showing "all
# the fields the API returned" means contact and org fields, not credentials.
# A password hash or an access token is never demo material, and salary is
# called out as restricted in section 2.2 of the design document.
#
# new_password is handled separately: it is a credential, but it is the one the
# GUARDRAIL_SHOW_PASSWORD switch deliberately exposes.
HARD_SECRET_MARKERS = [
    "passwordhash",
    "passwordprofile",
    "passwd",
    "pwd",
    "secret",
    "token",
    "credential",
    "mfa",
    "securityquestion",
    "apikey",
    "privatekey",
    "ssn",
    "aadhaar",
    "creditcard",
    "salary",
    "compensation",
]


# ---------------------------------------------------------------------------
# 3.5 Rate Limiting
# ---------------------------------------------------------------------------
# Password resets allowed per target account inside the window.
RESET_RATE_LIMIT_COUNT = int(os.getenv("GUARDRAIL_RESET_LIMIT", "3"))
RESET_RATE_LIMIT_WINDOW_SECONDS = int(os.getenv("GUARDRAIL_RESET_WINDOW", "300"))


# ---------------------------------------------------------------------------
# 3.4 Confirmation Requirement
# ---------------------------------------------------------------------------
# Intents that need an explicit yes before the tool runs.
CONFIRMATION_REQUIRED_INTENTS: Set[str] = _env_set(
    "GUARDRAIL_CONFIRM_INTENTS",
    "password_reset",
)


# ---------------------------------------------------------------------------
# Shared user-facing messages
# ---------------------------------------------------------------------------
# Blocked requests get a generic message on purpose. A message that names the
# rule and what it matched tells someone probing the system exactly what to
# change. The specifics go to the audit log instead.
MSG_NOT_SUPPORTED = "Requested operation is currently not supported."
MSG_INVALID_INPUT = "The request could not be processed. Please check the user identifier and try again."
MSG_SINGLE_USER = "Please request one user at a time."
MSG_NOT_AUTHORIZED = "You are not authorized to perform this operation."
MSG_HIGH_PRIVILEGE = "Additional approval is required before this operation can be completed."
MSG_RATE_LIMITED = "Too many recent requests for this account. Please try again later."
MSG_PASSWORD_DELIVERED = (
    "Password reset completed successfully. "
    "Temporary credentials have been delivered through an approved channel."
)
