"""
Password Vault
Author: Amit Bhagat
Purpose: Hold an original temporary password server-side, so it never travels
         in an API response.

The specification says the original password may exist in only two places: the
downloaded TXT file, and the email sent to the manager after the operator
clicks the button. Both of those happen *after* the reset response has already
been returned, which leaves a problem: something has to remember the password
in between.

This module is that something. The reset stores the password here and puts a
short opaque token in the response. The download and email paths hand back the
token to retrieve it. The password itself is never serialised into a response,
never written to session state, and never logged.

Scope and limits:
    In-process and in-memory, which is correct for the demo and for a single
    Streamlit session. A multi-worker deployment needs this in Redis or another
    shared store, or a token issued by one worker will not resolve on another.
    Entries expire, so a token left unused simply stops working.
"""

from __future__ import annotations

import secrets
import threading
import time
from dataclasses import dataclass, field
from typing import Dict, Optional

from loguru import logger

# How long a token stays usable. Long enough for an operator to download the
# file and send the email, short enough that a forgotten browser tab does not
# leave a live credential in memory all day.
DEFAULT_TTL_SECONDS = 900


@dataclass
class VaultEntry:
    """One stored password and the details needed to act on it."""

    password: str
    username: str
    employee_name: str = ""
    manager_name: str = "Not Available"
    manager_email: str = "Not Available"
    created_at: float = field(default_factory=time.time)


class PasswordVault:
    """Short-lived, in-memory store for temporary passwords."""

    def __init__(self, ttl_seconds: int = DEFAULT_TTL_SECONDS) -> None:
        self.ttl_seconds = ttl_seconds
        self._entries: Dict[str, VaultEntry] = {}
        # Streamlit and FastAPI can both touch this from different threads.
        self._lock = threading.Lock()

    def store(
        self,
        password: str,
        username: str,
        employee_name: str = "",
        manager_name: str = "Not Available",
        manager_email: str = "Not Available",
    ) -> str:
        """
        Store a password and return the token that stands in for it.

        Args:
            password: The original temporary password.
            username: The account it belongs to.
            employee_name: Display name, used in the email body.
            manager_name: Manager's display name, used in the TXT and email.
            manager_email: Manager's address, used as the email recipient.

        Returns:
            An opaque token. Safe to put in an API response; it reveals nothing
            about the password it stands for.
        """
        self._evict_expired()

        token = secrets.token_urlsafe(16)

        with self._lock:
            self._entries[token] = VaultEntry(
                password=password,
                username=username,
                employee_name=employee_name,
                manager_name=manager_name,
                manager_email=manager_email,
            )

        # The token is logged, the password is not. That is the whole point of
        # the indirection.
        logger.info(
            "PASSWORD_VAULT_STORED | username={} | token={}",
            username,
            token,
        )

        return token

    def get(self, token: str) -> Optional[VaultEntry]:
        """
        Retrieve an entry by token.

        Args:
            token: The token issued by store().

        Returns:
            The entry, or None if the token is unknown or has expired.
        """
        self._evict_expired()

        with self._lock:
            entry = self._entries.get(token)

        if entry is None:
            logger.warning("PASSWORD_VAULT_MISS | token={}", token)

        return entry

    def discard(self, token: str) -> None:
        """
        Remove an entry once it is no longer needed.

        Args:
            token: The token to forget.
        """
        with self._lock:
            self._entries.pop(token, None)

        logger.info("PASSWORD_VAULT_DISCARDED | token={}", token)

    def _evict_expired(self) -> None:
        """Drop entries that have outlived the TTL."""
        cutoff = time.time() - self.ttl_seconds

        with self._lock:
            expired = [
                token
                for token, entry in self._entries.items()
                if entry.created_at < cutoff
            ]
            for token in expired:
                del self._entries[token]

        if expired:
            logger.info("PASSWORD_VAULT_EXPIRED | count={}", len(expired))


# One shared vault for the process.
password_vault = PasswordVault()
