"""Read-only connection factory for the external ITOM PostgreSQL database."""
from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Iterator

import psycopg
from psycopg.rows import dict_row


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required ITOM database setting: {name}")
    return value


def itom_configured() -> bool:
    return all(
        os.getenv(name, "").strip()
        for name in ("ITOM_DB_HOST", "ITOM_DB_NAME", "ITOM_DB_USER", "ITOM_DB_PASSWORD")
    )


@contextmanager
def itom_connection() -> Iterator[psycopg.Connection]:
    """Open one read-only ITOM connection and always close it."""
    connection = psycopg.connect(
        host=_required("ITOM_DB_HOST"),
        port=int(os.getenv("ITOM_DB_PORT", "5432")),
        dbname=_required("ITOM_DB_NAME"),
        user=_required("ITOM_DB_USER"),
        password=_required("ITOM_DB_PASSWORD"),
        connect_timeout=int(os.getenv("ITOM_DB_CONNECT_TIMEOUT_SECONDS", "10")),
        sslmode=os.getenv("ITOM_DB_SSLMODE", "prefer").strip() or "prefer",
        row_factory=dict_row,
        options="-c default_transaction_read_only=on",
    )
    try:
        yield connection
    finally:
        connection.close()
