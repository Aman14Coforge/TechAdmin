"""
Password Masking Utility
Author: Amit Bhagat
Purpose: Produce a display-safe version of a temporary password.

Change #1 of the enhancement specification.

Masking rule:
    - keep the first 4 characters
    - keep the last 2 characters
    - replace everything between them with '*'
    - if the password is 6 characters or shorter there is no middle, so the
      whole value is masked

Examples:
    Temp@12345  ->  Temp****45
    abc123      ->  ******

This module never logs the value it is given. A masked password is still
derived from a credential, and the specification forbids logging either form.
"""

from __future__ import annotations

VISIBLE_PREFIX = 4
VISIBLE_SUFFIX = 2
MASK_CHARACTER = "*"


def mask_password(password: str) -> str:
    """
    Return a masked form of a password, safe to show on screen.

    Args:
        password: The original password. Never logged, never stored by this
            function.

    Returns:
        The masked string. An empty or non-string input returns an empty
        string rather than raising, because a display helper should not be able
        to break a password reset that already succeeded.
    """
    if not password or not isinstance(password, str):
        return ""

    length = len(password)

    # Nothing would be hidden if the visible ends met or overlapped, so mask
    # the whole value instead of leaking it in full.
    if length <= VISIBLE_PREFIX + VISIBLE_SUFFIX:
        return MASK_CHARACTER * length

    middle_length = length - VISIBLE_PREFIX - VISIBLE_SUFFIX

    return (
        password[:VISIBLE_PREFIX]
        + MASK_CHARACTER * middle_length
        + password[-VISIBLE_SUFFIX:]
    )
