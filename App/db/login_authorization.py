"""
Login Authorization
Author: Amit Bhagat
Purpose: Decide whether an authenticated person is allowed into TechAdmin.

Signing in with Microsoft proves who someone is. It does not decide whether
they may use this application. That second decision is made here, against the
app_users table described in the RDBMS Audit and Operation Tracking design.

The rule:

    The display_name on the sign-in must match a display_name in app_users,
    and that row must be active. Anything else is refused.

Matching is case-insensitive and ignores surrounding whitespace, so
"Amit Bhagat", "amit bhagat" and " Amit Bhagat " all resolve to the same row.

A database that cannot be reached is treated as a refusal rather than an
allowance. An audit system that fails open would let anyone in for exactly as
long as the outage lasts.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from loguru import logger
from sqlalchemy import func, select

from App.db.connection import SessionLocal
from App.db.models.app_users import AppUser


@dataclass
class AccessDecision:
    """
    The outcome of checking one signed-in person against app_users.

    Attributes:
        allowed: Whether the person may use TechAdmin.
        reason: Machine-readable outcome, for the audit log.
        message: Text shown on the sign-in screen.
        display_name: The name that was checked.
        user_principal_name: The UPN from the matched row, when there is one.
        user_id: The app_users primary key, when there is one.
        department: Department from the matched row, when present.
    """

    allowed: bool
    reason: str
    message: str = ""
    display_name: str = ""
    user_principal_name: str = ""
    user_id: str = ""
    department: str = ""


MSG_NOT_IN_DATABASE = (
    "User not found in database. You are not an authenticated TechAdmin user."
)

MSG_INACTIVE = (
    "This TechAdmin account is inactive. Contact the platform administrator."
)

MSG_NO_NAME = (
    "The sign-in did not provide a display name, so access cannot be verified."
)

MSG_DIRECTORY_UNAVAILABLE = (
    "The TechAdmin user directory is unavailable, so access cannot be "
    "verified. Please try again later."
)


def extract_display_name(claims: Dict[str, Any]) -> str:
    """
    Pull the display name out of the sign-in claims.

    Entra puts the person's full name in "name". The local test account sets
    the same key, so one function covers both sign-in paths.

    Args:
        claims: The claims dict from Entra, or from the local test account.

    Returns:
        The display name, or an empty string when none was supplied.
    """
    if not isinstance(claims, dict):
        return ""

    for key in ("name", "display_name", "preferred_username"):
        value = claims.get(key)
        if value and str(value).strip():
            return str(value).strip()

    return ""


def authorize_display_name(display_name: str) -> AccessDecision:
    """
    Check one display name against the app_users table.

    Args:
        display_name: The name taken from the sign-in claims.

    Returns:
        An AccessDecision. Never raises: a database problem is reported as a
        refusal rather than being allowed to reach the caller as an exception.
    """
    name = (display_name or "").strip()

    if not name:
        logger.warning("LOGIN_DENIED | reason=no_display_name")
        return AccessDecision(
            allowed=False,
            reason="no_display_name",
            message=MSG_NO_NAME,
        )

    try:
        with SessionLocal() as session:
            # lower() on both sides so the comparison is case-insensitive in
            # the database rather than after loading every row.
            statement = select(AppUser).where(
                func.lower(func.trim(AppUser.display_name)) == name.lower()
            )
            user = session.execute(statement).scalars().first()

    except Exception as exc:
        # Fail closed. An unreachable directory must not become an open door.
        logger.error(
            "LOGIN_DENIED | display_name={} | reason=directory_unavailable | error_type={}",
            name,
            type(exc).__name__,
        )
        return AccessDecision(
            allowed=False,
            reason="directory_unavailable",
            message=MSG_DIRECTORY_UNAVAILABLE,
            display_name=name,
        )

    if user is None:
        logger.warning(
            "LOGIN_DENIED | display_name={} | reason=not_found_in_app_users",
            name,
        )
        return AccessDecision(
            allowed=False,
            reason="not_found_in_app_users",
            message=MSG_NOT_IN_DATABASE,
            display_name=name,
        )

    if not user.is_active:
        logger.warning(
            "LOGIN_DENIED | display_name={} | user_id={} | reason=inactive",
            name,
            user.user_id,
        )
        return AccessDecision(
            allowed=False,
            reason="inactive",
            message=MSG_INACTIVE,
            display_name=name,
            user_id=str(user.user_id),
        )

    logger.info(
        "USER AUTHENTICATED | display_name={} | user_principal_name={} | "
        "user_id={} | department={}",
        user.display_name,
        user.user_principal_name,
        user.user_id,
        user.department or "not set",
    )

    return AccessDecision(
        allowed=True,
        reason="authenticated",
        message="",
        display_name=user.display_name,
        user_principal_name=user.user_principal_name,
        user_id=str(user.user_id),
        department=user.department or "",
    )


def authorize_claims(claims: Dict[str, Any]) -> AccessDecision:
    """
    Check a set of sign-in claims against app_users.

    Args:
        claims: The claims dict from either sign-in path.

    Returns:
        An AccessDecision.
    """
    return authorize_display_name(extract_display_name(claims))
