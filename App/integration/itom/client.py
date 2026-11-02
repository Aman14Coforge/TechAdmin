"""Read-only ITOM database client for the Infrastructure Agent.

Only the two bundled queries in ``sql/`` are ever executed, and every session
is opened with ``default_transaction_read_only=on`` so the database itself
rejects any write.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional
from urllib.parse import quote_plus

from loguru import logger

from App.integration.itom.config import ItomConfig

SQL_DIR = Path(__file__).resolve().parent / "sql"
SITE_SCORES_SQL = "site_scores.sql"
SITE_ALERTS_SQL = "site_alerts.sql"

_WRITE_KEYWORDS = re.compile(
    r"\b(insert|update|delete|merge|drop|alter|create|truncate|grant|revoke|copy|call|do|vacuum|refresh)\b",
    re.IGNORECASE,
)


def _strip_sql_comments(sql: str) -> str:
    sql = re.sub(r"/\*.*?\*/", " ", sql, flags=re.DOTALL)
    return re.sub(r"--[^\n]*", " ", sql)


def assert_read_only_sql(sql: str) -> None:
    """Reject anything that is not a single SELECT/WITH statement."""
    body = _strip_sql_comments(sql).strip().rstrip(";").strip()
    if not re.match(r"^(with|select)\b", body, re.IGNORECASE):
        raise ValueError("Only SELECT queries may run against the ITOM database.")
    if ";" in body:
        raise ValueError("Only a single statement may run against the ITOM database.")
    if _WRITE_KEYWORDS.search(body):
        raise ValueError("Write statements are not allowed against the ITOM database.")


@lru_cache(maxsize=None)
def load_query(file_name: str) -> str:
    sql = (SQL_DIR / file_name).read_text(encoding="utf-8")
    assert_read_only_sql(sql)
    return sql


def format_interval(value: timedelta | None) -> str | None:
    """Render a PostgreSQL interval as '2d 3h 4m'."""
    if value is None:
        return None
    seconds = int(value.total_seconds())
    if seconds < 0:
        return "0m"
    days, seconds = divmod(seconds, 86400)
    hours, seconds = divmod(seconds, 3600)
    minutes = seconds // 60
    parts = [f"{days}d"] if days else []
    if hours or days:
        parts.append(f"{hours}h")
    parts.append(f"{minutes}m")
    return " ".join(parts)


def _normalize_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, timedelta):
        return format_interval(value)
    if isinstance(value, datetime):
        return value.replace(microsecond=0)
    return value


def normalize_row(row: dict[str, Any]) -> dict[str, Any]:
    return {key: _normalize_value(value) for key, value in row.items()}


class ItomReadOnlyClient:
    """Run the Infrastructure Agent queries against the ITOM database."""

    def __init__(self, config: Optional[ItomConfig] = None) -> None:
        self.config = config or ItomConfig.from_env()
        self._engine = None

    @property
    def uses_mock_data(self) -> bool:
        return self.config.use_mock_data

    def _get_engine(self):
        if self._engine is None:
            from sqlalchemy import create_engine

            self.config.validate()
            url = (
                f"postgresql+psycopg://{self.config.user}:{quote_plus(self.config.password)}"
                f"@{self.config.host}:{self.config.port}/{self.config.name}"
            )
            self._engine = create_engine(
                url,
                pool_pre_ping=True,
                pool_size=2,
                max_overflow=2,
                connect_args={
                    "connect_timeout": self.config.connect_timeout_seconds,
                    "options": (
                        "-c default_transaction_read_only=on "
                        f"-c statement_timeout={self.config.statement_timeout_seconds * 1000}"
                    ),
                    "application_name": "techadmin-infrastructure-agent",
                },
            )
            logger.info("ITOM read-only engine created | {}", self.config.safe_summary())
        return self._engine

    def _run(self, file_name: str) -> list[dict[str, Any]]:
        from sqlalchemy import text

        sql = load_query(file_name)
        with self._get_engine().connect() as connection:
            result = connection.execute(text(sql))
            rows = [normalize_row(dict(row)) for row in result.mappings()]
            connection.rollback()
        logger.info("ITOM query completed | query={} | rows={}", file_name, len(rows))
        return rows

    def fetch_site_scores(self) -> list[dict[str, Any]]:
        """Query 2: one row per location with its combined score and device counts."""
        if self.uses_mock_data:
            from App.integration.itom.mock_data import mock_site_scores

            return mock_site_scores()
        return self._run(SITE_SCORES_SQL)

    def fetch_site_alerts(self) -> list[dict[str, Any]]:
        """Query 1: problem SolarWinds/Intune devices at critical and warning sites."""
        if self.uses_mock_data:
            from App.integration.itom.mock_data import mock_site_alerts

            return mock_site_alerts()
        return self._run(SITE_ALERTS_SQL)
