"""Read Security Agent query history for the shared TechAdmin sidebar."""
from __future__ import annotations
import threading
import uuid
from datetime import datetime, timezone
from typing import Any
from sqlalchemy import select
from App.db.connection import SessionLocal, engine
from App.db.models.security_agent_query import SecurityAgentQuery

_TABLE_LOCK=threading.Lock()
_TABLE_READY=False

def _ensure_table()->None:
    global _TABLE_READY
    if _TABLE_READY:return
    with _TABLE_LOCK:
        if _TABLE_READY:return
        SecurityAgentQuery.__table__.create(bind=engine,checkfirst=True)
        _TABLE_READY=True

def start_security_query(*,requester_id:str|None,requester_name:str|None,query_text:str,action:str|None,target:str|None=None,request_metadata:dict[str,Any]|None=None)->str|None:
    """Persist the request before work starts so recent history includes failures and pending jobs."""
    if not requester_id:return None
    try:
        _ensure_table()
        row=SecurityAgentQuery(requester_id=str(requester_id),requester_name=requester_name,query_text=query_text,
            action=action,target=target,status="running",request_metadata=request_metadata or {})
        with SessionLocal() as db:
            db.add(row);db.commit();db.refresh(row)
            return str(row.query_id)
    except Exception:
        from loguru import logger
        logger.exception("SECURITY_QUERY_AUDIT_START_FAILED")
        return None

def finish_security_query(query_id:str|None,*,status:str,response_summary:dict[str,Any]|None=None,error_message:str|None=None)->None:
    if not query_id:return
    try:
        _ensure_table()
        with SessionLocal() as db:
            row=db.get(SecurityAgentQuery,uuid.UUID(str(query_id)))
            if row:
                row.status=status;row.response_summary=response_summary or {};row.error_message=error_message
                row.completed_at=datetime.now(timezone.utc);db.commit()
    except Exception:
        from loguru import logger
        logger.exception("SECURITY_QUERY_AUDIT_FINISH_FAILED | query_id={}",query_id)


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
