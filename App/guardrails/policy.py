# # # """Environment-driven guardrail policy for TechAdmin."""
# # # from __future__ import annotations
# # # import os
# # # from typing import Set


# # # def _env_bool(name: str, default: bool) -> bool:
# # #     raw = os.getenv(name)
# # #     return default if raw is None else raw.strip().lower() in {"true", "1", "yes", "on"}


# # # def _env_set(name: str, default: str) -> Set[str]:
# # #     return {item.strip().lower() for item in os.getenv(name, default).split(",") if item.strip()}


# # # ALLOWED_INTENTS = _env_set(
# # #     "GUARDRAIL_ALLOWED_INTENTS",
# # #     "get_user_details,password_reset,account_unlock,grant_access,revoke_access,failed_login_investigation,create_user,delete_user,create_group,create_vm",
# # # )
# # # FORBIDDEN_OPERATION_PATTERNS = [
# # #     r"\bdelete\s+(all\s+)?(user|users|account|accounts)\b",
# # #     r"\bshut\s*down\b", r"\breboot\s+(the\s+)?server\b",
# # #     r"\bdrop\s+(table|database)\b",
# # #     r"\bdisable\s+(all\s+)?(user|users|account|accounts)\b",
# # #     r"\bgrant\s+(me\s+)?(admin|administrator|global\s+admin)\b",
# # # ]


# # # class Role:
# # #     EMPLOYEE = "employee"
# # #     HELPDESK = "helpdesk"
# # #     ADMIN = "admin"


# # # ROLE_PERMISSIONS = {
# # #     Role.EMPLOYEE: {"get_user_details"},
# # #     Role.HELPDESK: {
# # #         "get_user_details", "password_reset", "account_unlock",
# # #         "grant_access", "revoke_access", "failed_login_investigation",
# # #     },
# # #     Role.ADMIN: {
# # #         "get_user_details", "password_reset", "account_unlock",
# # #         "grant_access", "revoke_access", "failed_login_investigation",
# # #         "create_user", "delete_user", "create_group", "create_vm",
# # #     },
# # # }
# # # DEFAULT_ROLE = os.getenv("GUARDRAIL_DEFAULT_ROLE", Role.HELPDESK)
# # # PRIVILEGED_USERNAMES = _env_set("GUARDRAIL_PRIVILEGED_USERNAMES", "administrator,admin,root,breakglass,break-glass,emergency")
# # # PRIVILEGED_PATTERNS = ["domainadmin", "domain.admin", "globaladmin", "global.admin", "svc-", "svc.", "service.account", "serviceaccount", "breakglass", "break-glass", "-admin", ".admin", "_admin"]
# # # PRIVILEGED_JOB_TITLES = _env_set("GUARDRAIL_PRIVILEGED_TITLES", "ceo,cto,cfo,coo,chief executive officer,chief technology officer,chief financial officer,chief operating officer,president,managing director,domain administrator,global administrator")
# # # SHOW_ALL_USER_FIELDS = _env_bool("GUARDRAIL_SHOW_ALL_USER_FIELDS", True)
# # # SHOW_TEMPORARY_PASSWORD = _env_bool("GUARDRAIL_SHOW_PASSWORD", True)
# # # ALLOWED_USER_FIELDS = {"id", "displayName", "userPrincipalName", "mail", "department", "jobTitle", "manager", "accountEnabled", "userType", "officeLocation"}
# # # SENSITIVE_FIELD_MARKERS = ["password", "passwd", "pwd", "secret", "token", "credential", "salary", "compensation", "mfa", "securityquestion", "security_question", "apikey", "api_key", "privatekey", "private_key", "ssn", "aadhaar", "creditcard", "credit_card", "homeaddress", "home_address", "streetaddress", "street_address", "mobilephone", "personal_email"]
# # # HARD_SECRET_MARKERS = ["passwordhash", "passwordprofile", "passwd", "pwd", "secret", "token", "credential", "mfa", "securityquestion", "apikey", "privatekey", "ssn", "aadhaar", "creditcard", "salary", "compensation"]
# # # RESET_RATE_LIMIT_COUNT = int(os.getenv("GUARDRAIL_RESET_LIMIT", "3"))
# # # RESET_RATE_LIMIT_WINDOW_SECONDS = int(os.getenv("GUARDRAIL_RESET_WINDOW", "300"))
# # # CONFIRMATION_REQUIRED_INTENTS = _env_set("GUARDRAIL_CONFIRM_INTENTS", "password_reset,revoke_access,delete_user")
# # # MSG_NOT_SUPPORTED = "Requested operation is currently not supported."
# # # MSG_INVALID_INPUT = "The request could not be processed. Please check the user identifier and try again."
# # # MSG_SINGLE_USER = "Please request one user at a time."
# # # MSG_NOT_AUTHORIZED = "You are not authorized to perform this operation."
# # # MSG_HIGH_PRIVILEGE = "Additional approval is required before this operation can be completed."
# # # MSG_RATE_LIMITED = "Too many recent requests for this account. Please try again later."
# # # MSG_PASSWORD_DELIVERED = "Password reset completed successfully. Temporary credentials have been delivered through an approved channel."


# # """Environment-driven guardrail policy for TechAdmin."""
# # from __future__ import annotations
# # import os
# # from typing import Set


# # def _env_bool(name: str, default: bool) -> bool:
# #     raw = os.getenv(name)
# #     return default if raw is None else raw.strip().lower() in {"true", "1", "yes", "on"}


# # def _env_set(name: str, default: str) -> Set[str]:
# #     return {item.strip().lower() for item in os.getenv(name, default).split(",") if item.strip()}


# # ALLOWED_INTENTS = _env_set(
# #     "GUARDRAIL_ALLOWED_INTENTS",
# #     "get_user_details,password_reset,account_unlock,grant_access,revoke_access,failed_login_investigation,create_user,delete_user,create_group,create_vm",
# # )
# # FORBIDDEN_OPERATION_PATTERNS = [
# #     r"\bdelete\s+(all\s+)?(user|users|account|accounts)\b",
# #     r"\bshut\s*down\b", r"\breboot\s+(the\s+)?server\b",
# #     r"\bdrop\s+(table|database)\b",
# #     r"\bdisable\s+(all\s+)?(user|users|account|accounts)\b",
# #     r"\bgrant\s+(me\s+)?(admin|administrator|global\s+admin)\b",
# # ]


# # class Role:
# #     EMPLOYEE = "employee"
# #     HELPDESK = "helpdesk"
# #     ADMIN = "admin"


# # ROLE_PERMISSIONS = {
# #     Role.EMPLOYEE: {"get_user_details"},
# #     Role.HELPDESK: {
# #         "get_user_details", "password_reset", "account_unlock",
# #         "grant_access", "revoke_access", "failed_login_investigation",
# #     },
# #     Role.ADMIN: {
# #         "get_user_details", "password_reset", "account_unlock",
# #         "grant_access", "revoke_access", "failed_login_investigation",
# #         "create_user", "delete_user", "create_group", "create_vm",
# #     },
# # }
# # DEFAULT_ROLE = os.getenv("GUARDRAIL_DEFAULT_ROLE", Role.HELPDESK)
# # PRIVILEGED_USERNAMES = _env_set("GUARDRAIL_PRIVILEGED_USERNAMES", "administrator,admin,root,breakglass,break-glass,emergency")
# # PRIVILEGED_PATTERNS = ["domainadmin", "domain.admin", "globaladmin", "global.admin", "svc-", "svc.", "service.account", "serviceaccount", "breakglass", "break-glass", "-admin", ".admin", "_admin"]
# # PRIVILEGED_JOB_TITLES = _env_set("GUARDRAIL_PRIVILEGED_TITLES", "ceo,cto,cfo,coo,chief executive officer,chief technology officer,chief financial officer,chief operating officer,president,managing director,domain administrator,global administrator")
# # SHOW_ALL_USER_FIELDS = _env_bool("GUARDRAIL_SHOW_ALL_USER_FIELDS", True)
# # SHOW_TEMPORARY_PASSWORD = _env_bool("GUARDRAIL_SHOW_PASSWORD", True)
# # ALLOWED_USER_FIELDS = {"id", "displayName", "userPrincipalName", "mail", "department", "jobTitle", "manager", "accountEnabled", "userType", "officeLocation"}
# # SENSITIVE_FIELD_MARKERS = ["password", "passwd", "pwd", "secret", "token", "credential", "salary", "compensation", "mfa", "securityquestion", "security_question", "apikey", "api_key", "privatekey", "private_key", "ssn", "aadhaar", "creditcard", "credit_card", "homeaddress", "home_address", "streetaddress", "street_address", "mobilephone", "personal_email"]
# # # --- ADDED FOR PASSWORD ENHANCEMENTS (Amit Bhagat) ---
# # # Field names that survive redaction despite containing a blocked substring.
# # # masked_password is already masked, and password_token is an opaque handle
# # # that reveals nothing on its own. Without this both would be blanked out by
# # # the "password" and "token" markers and the UI would have nothing to show.
# # DISPLAY_SAFE_FIELDS = {"masked_password", "password_token"}
# # # --- END ADDED FOR PASSWORD ENHANCEMENTS ---
# # HARD_SECRET_MARKERS = ["passwordhash", "passwordprofile", "passwd", "pwd", "secret", "token", "credential", "mfa", "securityquestion", "apikey", "privatekey", "ssn", "aadhaar", "creditcard", "salary", "compensation"]
# # RESET_RATE_LIMIT_COUNT = int(os.getenv("GUARDRAIL_RESET_LIMIT", "3"))
# # RESET_RATE_LIMIT_WINDOW_SECONDS = int(os.getenv("GUARDRAIL_RESET_WINDOW", "300"))
# # CONFIRMATION_REQUIRED_INTENTS = _env_set("GUARDRAIL_CONFIRM_INTENTS", "password_reset,revoke_access,delete_user")
# # MSG_NOT_SUPPORTED = "Requested operation is currently not supported."
# # MSG_INVALID_INPUT = "The request could not be processed. Please check the user identifier and try again."
# # MSG_SINGLE_USER = "Please request one user at a time."
# # MSG_NOT_AUTHORIZED = "You are not authorized to perform this operation."
# # MSG_HIGH_PRIVILEGE = "Additional approval is required before this operation can be completed."
# # MSG_RATE_LIMITED = "Too many recent requests for this account. Please try again later."
# # MSG_PASSWORD_DELIVERED = "Password reset completed successfully. Temporary credentials have been delivered through an approved channel."


# """Environment-driven guardrail policy for TechAdmin."""
# from __future__ import annotations
# import os
# from typing import Set


# def _env_bool(name: str, default: bool) -> bool:
#     raw = os.getenv(name)
#     return default if raw is None else raw.strip().lower() in {"true", "1", "yes", "on"}


# def _env_set(name: str, default: str) -> Set[str]:
#     return {item.strip().lower() for item in os.getenv(name, default).split(",") if item.strip()}


# ALLOWED_INTENTS = _env_set(
#     "GUARDRAIL_ALLOWED_INTENTS",
#     "get_user_details,password_reset,account_unlock,grant_access,revoke_access,failed_login_investigation,create_user,delete_user,create_group,create_vm",
# )
# FORBIDDEN_OPERATION_PATTERNS = [
#     r"\bdelete\s+(all\s+)?(user|users|account|accounts)\b",
#     r"\bshut\s*down\b", r"\breboot\s+(the\s+)?server\b",
#     r"\bdrop\s+(table|database)\b",
#     r"\bdisable\s+(all\s+)?(user|users|account|accounts)\b",
#     r"\bgrant\s+(me\s+)?(admin|administrator|global\s+admin)\b",
# ]


# class Role:
#     EMPLOYEE = "employee"
#     HELPDESK = "helpdesk"
#     ADMIN = "admin"


# ROLE_PERMISSIONS = {
#     Role.EMPLOYEE: {"get_user_details"},
#     Role.HELPDESK: {
#         "get_user_details", "password_reset", "account_unlock",
#         "grant_access", "revoke_access", "failed_login_investigation",
#     },
#     Role.ADMIN: {
#         "get_user_details", "password_reset", "account_unlock",
#         "grant_access", "revoke_access", "failed_login_investigation",
#         "create_user", "delete_user", "create_group", "create_vm",
#     },
# }
# DEFAULT_ROLE = os.getenv("GUARDRAIL_DEFAULT_ROLE", Role.HELPDESK)
# PRIVILEGED_USERNAMES = _env_set("GUARDRAIL_PRIVILEGED_USERNAMES", "administrator,admin,root,breakglass,break-glass,emergency")
# PRIVILEGED_PATTERNS = ["domainadmin", "domain.admin", "globaladmin", "global.admin", "svc-", "svc.", "service.account", "serviceaccount", "breakglass", "break-glass", "-admin", ".admin", "_admin"]
# PRIVILEGED_JOB_TITLES = _env_set("GUARDRAIL_PRIVILEGED_TITLES", "ceo,cto,cfo,coo,chief executive officer,chief technology officer,chief financial officer,chief operating officer,president,managing director,domain administrator,global administrator")
# SHOW_ALL_USER_FIELDS = _env_bool("GUARDRAIL_SHOW_ALL_USER_FIELDS", True)
# # CHANGED FOR PASSWORD ENHANCEMENTS (Amit Bhagat): now defaults to False. The
# # specification forbids the original password in any API response or on the UI,
# # so the earlier demo default would defeat the masking. Turning this back on
# # does not restore the old behaviour either: the reset tool no longer emits an
# # original password field at all.
# SHOW_TEMPORARY_PASSWORD = _env_bool("GUARDRAIL_SHOW_PASSWORD", False)
# ALLOWED_USER_FIELDS = {"id", "displayName", "userPrincipalName", "mail", "department", "jobTitle", "manager", "accountEnabled", "userType", "officeLocation"}
# SENSITIVE_FIELD_MARKERS = ["password", "passwd", "pwd", "secret", "token", "credential", "salary", "compensation", "mfa", "securityquestion", "security_question", "apikey", "api_key", "privatekey", "private_key", "ssn", "aadhaar", "creditcard", "credit_card", "homeaddress", "home_address", "streetaddress", "street_address", "mobilephone", "personal_email"]
# # --- ADDED FOR PASSWORD ENHANCEMENTS (Amit Bhagat) ---
# # Field names that survive redaction despite containing a blocked substring.
# # masked_password is already masked, and password_token is an opaque handle
# # that reveals nothing on its own. Without this both would be blanked out by
# # the "password" and "token" markers and the UI would have nothing to show.
# DISPLAY_SAFE_FIELDS = {"masked_password", "password_token"}
# # --- END ADDED FOR PASSWORD ENHANCEMENTS ---
# # ADDED FOR PASSWORD ENHANCEMENTS (Amit Bhagat): "_transient_password" is the
# # internal key that carries the password across the MCP process boundary.
# # demo_flow strips it, but listing it here means that even if a caller skips
# # that step the value can never be restored into a response.
# HARD_SECRET_MARKERS = ["transientpassword", "passwordhash", "passwordprofile", "passwd", "pwd", "secret", "token", "credential", "mfa", "securityquestion", "apikey", "privatekey", "ssn", "aadhaar", "creditcard", "salary", "compensation"]
# RESET_RATE_LIMIT_COUNT = int(os.getenv("GUARDRAIL_RESET_LIMIT", "3"))
# RESET_RATE_LIMIT_WINDOW_SECONDS = int(os.getenv("GUARDRAIL_RESET_WINDOW", "300"))
# CONFIRMATION_REQUIRED_INTENTS = _env_set("GUARDRAIL_CONFIRM_INTENTS", "password_reset,revoke_access,delete_user")
# MSG_NOT_SUPPORTED = "Requested operation is currently not supported."
# MSG_INVALID_INPUT = "The request could not be processed. Please check the user identifier and try again."
# MSG_SINGLE_USER = "Please request one user at a time."
# MSG_NOT_AUTHORIZED = "You are not authorized to perform this operation."
# MSG_HIGH_PRIVILEGE = "Additional approval is required before this operation can be completed."
# MSG_RATE_LIMITED = "Too many recent requests for this account. Please try again later."
# MSG_PASSWORD_DELIVERED = "Password reset completed successfully. Temporary credentials have been delivered through an approved channel."


# # """Environment-driven guardrail policy for TechAdmin."""
# # from __future__ import annotations
# # import os
# # from typing import Set


# # def _env_bool(name: str, default: bool) -> bool:
# #     raw = os.getenv(name)
# #     return default if raw is None else raw.strip().lower() in {"true", "1", "yes", "on"}


# # def _env_set(name: str, default: str) -> Set[str]:
# #     return {item.strip().lower() for item in os.getenv(name, default).split(",") if item.strip()}


# # ALLOWED_INTENTS = _env_set(
# #     "GUARDRAIL_ALLOWED_INTENTS",
# #     "get_user_details,password_reset,account_unlock,grant_access,revoke_access,failed_login_investigation,create_user,delete_user,create_group,create_vm",
# # )
# # FORBIDDEN_OPERATION_PATTERNS = [
# #     r"\bdelete\s+(all\s+)?(user|users|account|accounts)\b",
# #     r"\bshut\s*down\b", r"\breboot\s+(the\s+)?server\b",
# #     r"\bdrop\s+(table|database)\b",
# #     r"\bdisable\s+(all\s+)?(user|users|account|accounts)\b",
# #     r"\bgrant\s+(me\s+)?(admin|administrator|global\s+admin)\b",
# # ]


# # class Role:
# #     EMPLOYEE = "employee"
# #     HELPDESK = "helpdesk"
# #     ADMIN = "admin"


# # ROLE_PERMISSIONS = {
# #     Role.EMPLOYEE: {"get_user_details"},
# #     Role.HELPDESK: {
# #         "get_user_details", "password_reset", "account_unlock",
# #         "grant_access", "revoke_access", "failed_login_investigation",
# #     },
# #     Role.ADMIN: {
# #         "get_user_details", "password_reset", "account_unlock",
# #         "grant_access", "revoke_access", "failed_login_investigation",
# #         "create_user", "delete_user", "create_group", "create_vm",
# #     },
# # }
# # DEFAULT_ROLE = os.getenv("GUARDRAIL_DEFAULT_ROLE", Role.HELPDESK)
# # PRIVILEGED_USERNAMES = _env_set("GUARDRAIL_PRIVILEGED_USERNAMES", "administrator,admin,root,breakglass,break-glass,emergency")
# # PRIVILEGED_PATTERNS = ["domainadmin", "domain.admin", "globaladmin", "global.admin", "svc-", "svc.", "service.account", "serviceaccount", "breakglass", "break-glass", "-admin", ".admin", "_admin"]
# # PRIVILEGED_JOB_TITLES = _env_set("GUARDRAIL_PRIVILEGED_TITLES", "ceo,cto,cfo,coo,chief executive officer,chief technology officer,chief financial officer,chief operating officer,president,managing director,domain administrator,global administrator")
# # SHOW_ALL_USER_FIELDS = _env_bool("GUARDRAIL_SHOW_ALL_USER_FIELDS", True)
# # SHOW_TEMPORARY_PASSWORD = _env_bool("GUARDRAIL_SHOW_PASSWORD", True)
# # ALLOWED_USER_FIELDS = {"id", "displayName", "userPrincipalName", "mail", "department", "jobTitle", "manager", "accountEnabled", "userType", "officeLocation"}
# # SENSITIVE_FIELD_MARKERS = ["password", "passwd", "pwd", "secret", "token", "credential", "salary", "compensation", "mfa", "securityquestion", "security_question", "apikey", "api_key", "privatekey", "private_key", "ssn", "aadhaar", "creditcard", "credit_card", "homeaddress", "home_address", "streetaddress", "street_address", "mobilephone", "personal_email"]
# # HARD_SECRET_MARKERS = ["passwordhash", "passwordprofile", "passwd", "pwd", "secret", "token", "credential", "mfa", "securityquestion", "apikey", "privatekey", "ssn", "aadhaar", "creditcard", "salary", "compensation"]
# # RESET_RATE_LIMIT_COUNT = int(os.getenv("GUARDRAIL_RESET_LIMIT", "3"))
# # RESET_RATE_LIMIT_WINDOW_SECONDS = int(os.getenv("GUARDRAIL_RESET_WINDOW", "300"))
# # CONFIRMATION_REQUIRED_INTENTS = _env_set("GUARDRAIL_CONFIRM_INTENTS", "password_reset,revoke_access,delete_user")
# # MSG_NOT_SUPPORTED = "Requested operation is currently not supported."
# # MSG_INVALID_INPUT = "The request could not be processed. Please check the user identifier and try again."
# # MSG_SINGLE_USER = "Please request one user at a time."
# # MSG_NOT_AUTHORIZED = "You are not authorized to perform this operation."
# # MSG_HIGH_PRIVILEGE = "Additional approval is required before this operation can be completed."
# # MSG_RATE_LIMITED = "Too many recent requests for this account. Please try again later."
# # MSG_PASSWORD_DELIVERED = "Password reset completed successfully. Temporary credentials have been delivered through an approved channel."


# """Environment-driven guardrail policy for TechAdmin."""
# from __future__ import annotations
# import os
# from typing import Set


# def _env_bool(name: str, default: bool) -> bool:
#     raw = os.getenv(name)
#     return default if raw is None else raw.strip().lower() in {"true", "1", "yes", "on"}


# def _env_set(name: str, default: str) -> Set[str]:
#     return {item.strip().lower() for item in os.getenv(name, default).split(",") if item.strip()}


# ALLOWED_INTENTS = _env_set(
#     "GUARDRAIL_ALLOWED_INTENTS",
#     "get_user_details,password_reset,account_unlock,grant_access,revoke_access,failed_login_investigation,create_user,delete_user,create_group,create_vm",
# )
# FORBIDDEN_OPERATION_PATTERNS = [
#     r"\bdelete\s+(all\s+)?(user|users|account|accounts)\b",
#     r"\bshut\s*down\b", r"\breboot\s+(the\s+)?server\b",
#     r"\bdrop\s+(table|database)\b",
#     r"\bdisable\s+(all\s+)?(user|users|account|accounts)\b",
#     r"\bgrant\s+(me\s+)?(admin|administrator|global\s+admin)\b",
# ]


# class Role:
#     EMPLOYEE = "employee"
#     HELPDESK = "helpdesk"
#     ADMIN = "admin"


# ROLE_PERMISSIONS = {
#     Role.EMPLOYEE: {"get_user_details"},
#     Role.HELPDESK: {
#         "get_user_details", "password_reset", "account_unlock",
#         "grant_access", "revoke_access", "failed_login_investigation",
#     },
#     Role.ADMIN: {
#         "get_user_details", "password_reset", "account_unlock",
#         "grant_access", "revoke_access", "failed_login_investigation",
#         "create_user", "delete_user", "create_group", "create_vm",
#     },
# }
# DEFAULT_ROLE = os.getenv("GUARDRAIL_DEFAULT_ROLE", Role.HELPDESK)
# PRIVILEGED_USERNAMES = _env_set("GUARDRAIL_PRIVILEGED_USERNAMES", "administrator,admin,root,breakglass,break-glass,emergency")
# PRIVILEGED_PATTERNS = ["domainadmin", "domain.admin", "globaladmin", "global.admin", "svc-", "svc.", "service.account", "serviceaccount", "breakglass", "break-glass", "-admin", ".admin", "_admin"]
# PRIVILEGED_JOB_TITLES = _env_set("GUARDRAIL_PRIVILEGED_TITLES", "ceo,cto,cfo,coo,chief executive officer,chief technology officer,chief financial officer,chief operating officer,president,managing director,domain administrator,global administrator")
# SHOW_ALL_USER_FIELDS = _env_bool("GUARDRAIL_SHOW_ALL_USER_FIELDS", True)
# SHOW_TEMPORARY_PASSWORD = _env_bool("GUARDRAIL_SHOW_PASSWORD", True)
# ALLOWED_USER_FIELDS = {"id", "displayName", "userPrincipalName", "mail", "department", "jobTitle", "manager", "accountEnabled", "userType", "officeLocation"}
# SENSITIVE_FIELD_MARKERS = ["password", "passwd", "pwd", "secret", "token", "credential", "salary", "compensation", "mfa", "securityquestion", "security_question", "apikey", "api_key", "privatekey", "private_key", "ssn", "aadhaar", "creditcard", "credit_card", "homeaddress", "home_address", "streetaddress", "street_address", "mobilephone", "personal_email"]
# # --- ADDED FOR PASSWORD ENHANCEMENTS (Amit Bhagat) ---
# # Field names that survive redaction despite containing a blocked substring.
# # masked_password is already masked, and password_token is an opaque handle
# # that reveals nothing on its own. Without this both would be blanked out by
# # the "password" and "token" markers and the UI would have nothing to show.
# DISPLAY_SAFE_FIELDS = {"masked_password", "password_token"}
# # --- END ADDED FOR PASSWORD ENHANCEMENTS ---
# HARD_SECRET_MARKERS = ["passwordhash", "passwordprofile", "passwd", "pwd", "secret", "token", "credential", "mfa", "securityquestion", "apikey", "privatekey", "ssn", "aadhaar", "creditcard", "salary", "compensation"]
# RESET_RATE_LIMIT_COUNT = int(os.getenv("GUARDRAIL_RESET_LIMIT", "3"))
# RESET_RATE_LIMIT_WINDOW_SECONDS = int(os.getenv("GUARDRAIL_RESET_WINDOW", "300"))
# CONFIRMATION_REQUIRED_INTENTS = _env_set("GUARDRAIL_CONFIRM_INTENTS", "password_reset,revoke_access,delete_user")
# MSG_NOT_SUPPORTED = "Requested operation is currently not supported."
# MSG_INVALID_INPUT = "The request could not be processed. Please check the user identifier and try again."
# MSG_SINGLE_USER = "Please request one user at a time."
# MSG_NOT_AUTHORIZED = "You are not authorized to perform this operation."
# MSG_HIGH_PRIVILEGE = "Additional approval is required before this operation can be completed."
# MSG_RATE_LIMITED = "Too many recent requests for this account. Please try again later."
# MSG_PASSWORD_DELIVERED = "Password reset completed successfully. Temporary credentials have been delivered through an approved channel."


"""Environment-driven guardrail policy for TechAdmin."""
from __future__ import annotations
import os
from typing import Set


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    return default if raw is None else raw.strip().lower() in {"true", "1", "yes", "on"}


def _env_set(name: str, default: str) -> Set[str]:
    return {item.strip().lower() for item in os.getenv(name, default).split(",") if item.strip()}


ALLOWED_INTENTS = _env_set(
    "GUARDRAIL_ALLOWED_INTENTS",
    "get_user_details,password_reset,account_unlock,grant_access,revoke_access,failed_login_investigation,create_user,delete_user,create_group,create_vm",
)
FORBIDDEN_OPERATION_PATTERNS = [
    r"\bdelete\s+(all\s+)?(user|users|account|accounts)\b",
    r"\bshut\s*down\b", r"\breboot\s+(the\s+)?server\b",
    r"\bdrop\s+(table|database)\b",
    r"\bdisable\s+(all\s+)?(user|users|account|accounts)\b",
    r"\bgrant\s+(me\s+)?(admin|administrator|global\s+admin)\b",
]


# ---------------------------------------------------------------------------
# --- ADDED FOR FULL EMAIL REQUIREMENT (Amit Bhagat) ---
# Both supported operations must name the target by complete email address.
# A bare username such as "amit.bhagat" is refused.
#
# Reason: a bare username is ambiguous. It can match more than one directory
# object, and it is the phrasing most likely to resolve to the wrong person on
# an operation that changes an account. Requiring the full address makes the
# target unmistakable before anything runs.
#
# Matching is case-insensitive, so Amit.Bhagat@Coforge.com,
# amit.bhagat@coforge.com and AMIT.BHAGAT@COFORGE.COM are all accepted.
#
# ALLOWED_EMAIL_DOMAINS restricts which domains may be targeted. Set it to an
# empty value to accept any well-formed address.
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
# --- END ADDED FOR FULL EMAIL REQUIREMENT ---



class Role:
    EMPLOYEE = "employee"
    HELPDESK = "helpdesk"
    ADMIN = "admin"


ROLE_PERMISSIONS = {
    Role.EMPLOYEE: {"get_user_details"},
    Role.HELPDESK: {
        "get_user_details", "password_reset", "account_unlock",
        "grant_access", "revoke_access", "failed_login_investigation",
    },
    Role.ADMIN: {
        "get_user_details", "password_reset", "account_unlock",
        "grant_access", "revoke_access", "failed_login_investigation",
        "create_user", "delete_user", "create_group", "create_vm",
    },
}
DEFAULT_ROLE = os.getenv("GUARDRAIL_DEFAULT_ROLE", Role.HELPDESK)
PRIVILEGED_USERNAMES = _env_set("GUARDRAIL_PRIVILEGED_USERNAMES", "administrator,admin,root,breakglass,break-glass,emergency")
PRIVILEGED_PATTERNS = ["domainadmin", "domain.admin", "globaladmin", "global.admin", "svc-", "svc.", "service.account", "serviceaccount", "breakglass", "break-glass", "-admin", ".admin", "_admin"]
PRIVILEGED_JOB_TITLES = _env_set("GUARDRAIL_PRIVILEGED_TITLES", "ceo,cto,cfo,coo,chief executive officer,chief technology officer,chief financial officer,chief operating officer,president,managing director,domain administrator,global administrator")
SHOW_ALL_USER_FIELDS = _env_bool("GUARDRAIL_SHOW_ALL_USER_FIELDS", True)
# CHANGED FOR PASSWORD ENHANCEMENTS (Amit Bhagat): now defaults to False. The
# specification forbids the original password in any API response or on the UI,
# so the earlier demo default would defeat the masking. Turning this back on
# does not restore the old behaviour either: the reset tool no longer emits an
# original password field at all.
SHOW_TEMPORARY_PASSWORD = _env_bool("GUARDRAIL_SHOW_PASSWORD", False)
ALLOWED_USER_FIELDS = {"id", "displayName", "userPrincipalName", "mail", "department", "jobTitle", "manager", "accountEnabled", "userType", "officeLocation"}
SENSITIVE_FIELD_MARKERS = ["password", "passwd", "pwd", "secret", "token", "credential", "salary", "compensation", "mfa", "securityquestion", "security_question", "apikey", "api_key", "privatekey", "private_key", "ssn", "aadhaar", "creditcard", "credit_card", "homeaddress", "home_address", "streetaddress", "street_address", "mobilephone", "personal_email"]
# --- ADDED FOR PASSWORD ENHANCEMENTS (Amit Bhagat) ---
# Field names that survive redaction despite containing a blocked substring.
# masked_password is already masked, and password_token is an opaque handle
# that reveals nothing on its own. Without this both would be blanked out by
# the "password" and "token" markers and the UI would have nothing to show.
DISPLAY_SAFE_FIELDS = {"masked_password", "password_token"}
# --- END ADDED FOR PASSWORD ENHANCEMENTS ---
# ADDED FOR PASSWORD ENHANCEMENTS (Amit Bhagat): "_transient_password" is the
# internal key that carries the password across the MCP process boundary.
# demo_flow strips it, but listing it here means that even if a caller skips
# that step the value can never be restored into a response.
HARD_SECRET_MARKERS = ["transientpassword", "passwordhash", "passwordprofile", "passwd", "pwd", "secret", "token", "credential", "mfa", "securityquestion", "apikey", "privatekey", "ssn", "aadhaar", "creditcard", "salary", "compensation"]
RESET_RATE_LIMIT_COUNT = int(os.getenv("GUARDRAIL_RESET_LIMIT", "3"))
RESET_RATE_LIMIT_WINDOW_SECONDS = int(os.getenv("GUARDRAIL_RESET_WINDOW", "300"))
CONFIRMATION_REQUIRED_INTENTS = _env_set("GUARDRAIL_CONFIRM_INTENTS", "password_reset,revoke_access,delete_user")
MSG_NOT_SUPPORTED = "Requested operation is currently not supported."
MSG_INVALID_INPUT = "The request could not be processed. Please check the user identifier and try again."
MSG_SINGLE_USER = "Please request one user at a time."
MSG_NOT_AUTHORIZED = "You are not authorized to perform this operation."
MSG_HIGH_PRIVILEGE = "Additional approval is required before this operation can be completed."
MSG_RATE_LIMITED = "Too many recent requests for this account. Please try again later."
MSG_PASSWORD_DELIVERED = "Password reset completed successfully. Temporary credentials have been delivered through an approved channel."
