"""Read Security Agent query history for the shared TechAdmin sidebar."""
from __future__ import annotations
from typing import Any
from sqlalchemy import select
from App.db.connection import SessionLocal
from App.db.models.security_agent_query import SecurityAgentQuery


def get_security_query_history(
    requester_id: str | None,
    *,
    limit: int = 20,
) -> list[dict[str, Any]]:
    if not requester_id:
        return []

    with SessionLocal() as db:
        rows = list(
            db.scalars(
                select(SecurityAgentQuery)
                .where(
                    SecurityAgentQuery.requester_id
                    == str(requester_id)
                )
                .order_by(
                    SecurityAgentQuery.created_at.desc()
                )
                .limit(max(1, min(int(limit), 100)))
            ).all()
        )

    return [
        {
            "request": row.query_text,
            "operation": row.action or "security_request",
            "target": row.target or "Security Agent",
            "status": row.status.casefold(),
            "requested_at": row.created_at,
            "agent": "security",
        }
        for row in rows
    ]
