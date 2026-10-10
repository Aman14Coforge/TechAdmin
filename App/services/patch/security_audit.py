from __future__ import annotations
from datetime import datetime, timezone
from typing import Any
from App.db.connection import SessionLocal
from App.db.models.security_agent_query import SecurityAgentQuery

class SecurityQueryAudit:
    @staticmethod
    def start(*, query: str, requester_id: str | None, requester_name: str | None) -> str:
        with SessionLocal() as db:
            row=SecurityAgentQuery(requester_id=requester_id,requester_name=requester_name,query_text=query,status="RECEIVED")
            db.add(row);db.commit();db.refresh(row);return str(row.query_id)
    @staticmethod
    def finish(query_id: str, *, action: str | None, target: str | None, status: str,
               metadata: dict[str,Any] | None=None, summary: dict[str,Any] | None=None,
               error: str | None=None) -> None:
        import uuid
        with SessionLocal() as db:
            row=db.get(SecurityAgentQuery,uuid.UUID(query_id))
            if not row:return
            row.action=action;row.target=target;row.status=status;row.request_metadata=metadata;row.response_summary=summary;row.error_message=error;row.completed_at=datetime.now(timezone.utc);db.commit()
