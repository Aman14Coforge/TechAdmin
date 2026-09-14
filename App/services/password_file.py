"""
Password TXT File Utility
Author: Amit Bhagat
Purpose: Build the downloadable TXT file described in Change #2.

The specification is explicit that the original password may appear inside this
file. That is the one place, alongside the manager email, where it is allowed
to exist. Nothing here is logged beyond success or failure and the filename.

File name:
    <username>_password.txt

Contents:
    Employee Username: john.doe
    Temporary Password: Temp@12345
    Manager Name: Jane Smith
    Manager Email: jane.smith@company.com
"""

from __future__ import annotations

import re
from typing import Optional, Tuple

from loguru import logger

NOT_AVAILABLE = "Not Available"

# Anything outside this set is replaced in the filename. A username arrives
# from Active Directory rather than from a form, but a filename built by string
# concatenation is still worth constraining.
_UNSAFE_FILENAME_CHARS = re.compile(r"[^A-Za-z0-9._\-]")


def build_password_filename(username: str) -> str:
    """
    Build the download filename for an account.

    Args:
        username: The employee's username.

    Returns:
        A filename of the form <username>_password.txt.
    """
    # The username reaching here can be a UPN (john.doe@company.com) when the
    # API backend ran, or a sAMAccountName (john.doe) when PowerShell did. The
    # specification's example is john.doe_password.txt, so the domain is
    # dropped to give one filename either way.
    account = (username or "user").strip().split("@", 1)[0]

    safe = _UNSAFE_FILENAME_CHARS.sub("_", account) or "user"
    return f"{safe}_password.txt"


def build_password_file_content(
    username: str,
    password: str,
    manager_name: str = NOT_AVAILABLE,
    manager_email: str = NOT_AVAILABLE,
) -> str:
    """
    Build the text content of the password file.

    Args:
        username: The employee's username.
        password: The original temporary password.
        manager_name: Manager display name, or "Not Available".
        manager_email: Manager address, or "Not Available".

    Returns:
        The file body as a string.
    """
    lines = [
        f"Employee Username: {username}",
        f"Temporary Password: {password}",
        f"Manager Name: {manager_name or NOT_AVAILABLE}",
        f"Manager Email: {manager_email or NOT_AVAILABLE}",
    ]

    return "\n".join(lines) + "\n"


def generate_password_file(
    username: str,
    password: str,
    manager_name: str = NOT_AVAILABLE,
    manager_email: str = NOT_AVAILABLE,
) -> Tuple[bool, Optional[str], Optional[str], str]:
    """
    Build the filename and content together, reporting failure rather than
    raising.

    The specification requires that a TXT generation failure must not bring
    down the application, so this returns a status instead of propagating an
    exception into the reset flow.

    Args:
        username: The employee's username.
        password: The original temporary password.
        manager_name: Manager display name.
        manager_email: Manager address.

    Returns:
        Tuple of (ok, filename, content, message). On failure filename and
        content are None and message explains what went wrong.
    """
    try:
        if not password:
            logger.warning(
                "TXT_GENERATION_FAILED | username={} | reason=no_password", username
            )
            return False, None, None, "No password was available to write."

        filename = build_password_filename(username)
        content = build_password_file_content(
            username=username,
            password=password,
            manager_name=manager_name,
            manager_email=manager_email,
        )

        # Filename and outcome are logged. The content is not, because it
        # contains the original password.
        logger.info("TXT_GENERATION_SUCCESS | username={} | filename={}", username, filename)

        return True, filename, content, "Password file generated."

    except Exception as exc:
        logger.error(
            "TXT_GENERATION_FAILED | username={} | error_type={}",
            username,
            type(exc).__name__,
        )
        return False, None, None, "Could not generate the password file."
