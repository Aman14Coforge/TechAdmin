"""Environment configuration for the read-only ITOM database connection."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ENV_FILE = Path(__file__).resolve().parents[3] / ".env"

TRUE_VALUES = {"1", "true", "yes", "y", "on"}


def _text(name: str, default: str = "") -> str:
    value = os.getenv(name)
    return default if value is None else value.strip()


@dataclass(frozen=True)
class ItomConfig:
    """Connection settings for the ITOM PostgreSQL database.

    The ITOM database is separate from the TechAdmin application database, so
    every setting uses its own ITOM_DB_* name and never reuses DB_PASSWORD.
    """

    host: str
    port: int
    name: str
    user: str
    password: str
    use_mock_data: bool
    connect_timeout_seconds: int
    statement_timeout_seconds: int
    cache_seconds: int

    @classmethod
    def from_env(cls) -> "ItomConfig":
        load_dotenv(ENV_FILE, override=False)
        return cls(
            host=_text("ITOM_DB_HOST", "172.18.51.38"),
            port=int(_text("ITOM_DB_PORT", "5432") or 5432),
            name=_text("ITOM_DB_NAME", "itom_db"),
            user=_text("ITOM_DB_USER", "itom_ro"),
            password=_text("ITOM_DB_PASSWORD"),
            use_mock_data=_text("ITOM_USE_MOCK_DATA", "false").casefold() in TRUE_VALUES,
            connect_timeout_seconds=int(_text("ITOM_DB_CONNECT_TIMEOUT_SECONDS", "10") or 10),
            statement_timeout_seconds=int(_text("ITOM_DB_STATEMENT_TIMEOUT_SECONDS", "60") or 60),
            cache_seconds=int(_text("ITOM_CACHE_SECONDS", "300") or 300),
        )

    def validate(self) -> None:
        if self.use_mock_data:
            return
        missing = [
            name
            for name, value in {
                "ITOM_DB_HOST": self.host,
                "ITOM_DB_NAME": self.name,
                "ITOM_DB_USER": self.user,
                "ITOM_DB_PASSWORD": self.password,
            }.items()
            if not value
        ]
        if missing:
            raise ValueError("Missing ITOM database settings: " + ", ".join(missing))

    def safe_summary(self) -> dict[str, object]:
        return {
            "host": self.host,
            "port": self.port,
            "name": self.name,
            "user": self.user,
            "password_set": bool(self.password),
            "use_mock_data": self.use_mock_data,
        }
