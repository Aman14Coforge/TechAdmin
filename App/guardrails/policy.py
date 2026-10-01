"""Environment-driven guardrail policy for TechAdmin."""
from __future__ import annotations

import os
from typing import Set


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    return default if raw is None else raw.strip().lower() in {
        "true", "1", "yes", "on",
    }


def _env_set(name: str, default: str) -> Set[str]:
    return {
        item.strip().lower()
        for item in os.getenv(name, default).split(",")
        if item.strip()
    }


# IMPORTANT: If GUARDRAIL_ALLOWED_INTENTS is explicitly defined in .env, it
# must also contain get_computer_details. The value below is only the default.
ALLOWED_INTENTS = _env_set(
    "GUARDRAIL_ALLOWED_INTENTS",
    (
        "get_user_details,get_computer_details,password_reset,account_unlock,"
        "grant_access,revoke_access,failed_login_investigation,create_user,"
        "delete_user,create_group,create_vm"
    ),
)

FORBIDDEN_OPERATION_PATTERNS = [
    r"\bdelete\s+(all\s+)?(user|users|account|accounts)\b",
    r"\bshut\s*down\b",
    r"\breboot\s+(the\s+)?server\b",
    r"\bdrop\s+(table|database)\b",
    r"\bdisable\s+(all\s+)?(user|users|account|accounts)\b",
    r"\bgrant\s+(me\s+)?(admin|administrator|global\s+admin)\b",
]


# ---------------------------------------------------------------------------
# Full email requirement
# ---------------------------------------------------------------------------

REQUIRE_FULL_EMAIL = _env_bool("GUARDRAIL_REQUIRE_FULL_EMAIL", True)

ALLOWED_EMAIL_DOMAINS: Set[str] = _env_set(
    "GUARDRAIL_ALLOWED_EMAIL_DOMAINS",
    "coforge.com",
)

MSG_FULL_EMAIL_REQUIRED = (
    "Please provide the complete email address, for example "
    "amit.bhagat@coforge.com."
)

MSG_DOMAIN_NOT_ALLOWED = (
    "That email address is outside the organisation. Please use a company "
    "email address."
)


class Role:
    EMPLOYEE = "employee"
    HELPDESK = "helpdesk"
    ADMIN = "admin"


ROLE_PERMISSIONS = {
    Role.EMPLOYEE: {
        "get_user_details",
    },
    Role.HELPDESK: {
        "get_user_details",
        "get_computer_details",
        "password_reset",
        "account_unlock",
        "grant_access",
        "revoke_access",
        "failed_login_investigation",
    },
    Role.ADMIN: {
        "get_user_details",
        "get_computer_details",
        "password_reset",
        "account_unlock",
        "grant_access",
        "revoke_access",
        "failed_login_investigation",
        "create_user",
        "delete_user",
        "create_group",
        "create_vm",
    },
}

DEFAULT_ROLE = os.getenv("GUARDRAIL_DEFAULT_ROLE", Role.HELPDESK)

PRIVILEGED_USERNAMES = _env_set(
    "GUARDRAIL_PRIVILEGED_USERNAMES",
    "administrator,admin,root,breakglass,break-glass,emergency",
)

PRIVILEGED_PATTERNS = [
    "domainadmin", "domain.admin", "globaladmin", "global.admin",
    "svc-", "svc.", "service.account", "serviceaccount",
    "breakglass", "break-glass", "-admin", ".admin", "_admin",
]

PRIVILEGED_JOB_TITLES = _env_set(
    "GUARDRAIL_PRIVILEGED_TITLES",
    (
        "ceo,cto,cfo,coo,chief executive officer,chief technology officer,"
        "chief financial officer,chief operating officer,president,"
        "managing director,domain administrator,global administrator"
    ),
)

SHOW_ALL_USER_FIELDS = _env_bool(
    "GUARDRAIL_SHOW_ALL_USER_FIELDS",
    True,
)

SHOW_TEMPORARY_PASSWORD = _env_bool(
    "GUARDRAIL_SHOW_PASSWORD",
    False,
)

ALLOWED_USER_FIELDS = {
    "id", "displayName", "userPrincipalName", "mail", "department",
    "jobTitle", "manager", "accountEnabled", "userType", "officeLocation",
    # Normalized/script user fields retained for existing Get User Details.
    "Success", "Name", "DisplayName", "SamAccountName", "UserPrincipalName",
    "Enabled", "LockedOut", "PasswordExpired", "PasswordLastSet",
    "PasswordNeverExpires", "BadPasswordCount", "DistinguishedName",
    "CanonicalName", "WhenCreated", "ManagerName", "ManagerDisplayName",
    "ManagerEmail", "ManagerMail", "ManagerUserPrincipalName",
    "PrimaryGroupName", "DirectGroups", "NestedGroups", "EffectiveGroups",
    "Mail", "MobilePhone", "Description", "Department",
}

# Dedicated allowlist for the computer dictionary under
# tool_result.result.computer. Unknown fields are withheld by default.
# The script returns a nested payload (DirectoryIdentity, LiveEndpoint, etc.)
# rather than flat fields, so the allowlist matches those top-level sections.
ALLOWED_COMPUTER_FIELDS = {
    "Success",
    "Query",
    "DirectoryIdentity",
    "DirectoryOperatingSystem",
    "DirectoryActivity",
    "OwnershipAndUsage",
    "DirectoryNetwork",
    "LiveEndpoint",
    "SecurityAndDelegation",
    "GroupMemberships",
    "CollectionContext",
}

SENSITIVE_FIELD_MARKERS = [
    "password", "passwd", "pwd", "secret", "token", "credential",
    "salary", "compensation", "mfa", "securityquestion",
    "security_question", "apikey", "api_key", "privatekey", "private_key",
    "ssn", "aadhaar", "creditcard", "credit_card", "homeaddress",
    "home_address", "streetaddress", "street_address", "mobilephone",
    "personal_email",
]

# password_token is opaque and masked_password is already masked. A computer
# account's PasswordLastSet is directory metadata, not a password value.
DISPLAY_SAFE_FIELDS = {
    "masked_password",
    "password_token",
    "PasswordLastSet",
}

HARD_SECRET_MARKERS = [
    "transientpassword", "passwordhash", "passwordprofile", "passwd", "pwd",
    "secret", "token", "credential", "mfa", "securityquestion", "apikey",
    "privatekey", "ssn", "aadhaar", "creditcard", "salary", "compensation",
]

RESET_RATE_LIMIT_COUNT = int(os.getenv("GUARDRAIL_RESET_LIMIT", "3"))
RESET_RATE_LIMIT_WINDOW_SECONDS = int(
    os.getenv("GUARDRAIL_RESET_WINDOW", "300")
)

CONFIRMATION_REQUIRED_INTENTS = _env_set(
    "GUARDRAIL_CONFIRM_INTENTS",
    "password_reset,revoke_access,delete_user",
)

MSG_NOT_SUPPORTED = "Requested operation is currently not supported."
MSG_INVALID_INPUT = (
    "The request could not be processed. Please check the target identifier "
    "and try again."
)
MSG_SINGLE_USER = "Please request one user at a time."
MSG_NOT_AUTHORIZED = "You are not authorized to perform this operation."
MSG_HIGH_PRIVILEGE = (
    "Additional approval is required before this operation can be completed."
)
MSG_RATE_LIMITED = (
    "Too many recent requests for this account. Please try again later."
)
MSG_PASSWORD_DELIVERED = (
    "Password reset completed successfully. Temporary credentials have been "
    "delivered through an approved channel."
)
