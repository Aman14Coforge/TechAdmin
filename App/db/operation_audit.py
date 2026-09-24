"""
Operation Request Auditing
Author: Amit Bhagat
Purpose: Record every TechAdmin request in operation_requests, and link it to
         the approved tool in operations.

All three audit tables are written from here:

    operations            the approved tool catalog, filled on first use of
                          each intent
    operation_requests    one row per request, linked to the catalog entry
    operation_executions  one row per actual execution attempt

The split between the last two is the one section 7 insists on:
operation_requests records what was asked for, operation_executions records
what the system actually attempted. A request that is blocked by the guardrails
or is waiting at a confirmation prompt has no execution row, because nothing
ran.

Two calls make up the lifecycle:

    open_request()      when the query arrives      -> status RECEIVED
    close_request()     when the flow returns       -> SUCCEEDED / FAILED /
                                                       AWAITING_APPROVAL /
                                                       REJECTED

Writing twice rather than once is deliberate. A single write at the end would
lose every request that crashed, timed out, or was abandoned mid-approval,
which are exactly the ones an audit trail exists to show.

Security, from section 7 of the design document. Nothing written here contains
a credential: no temporary password, no access token, no authorization header.
Target identifiers are masked before they are stored, and the request
parameters are reduced to the few fields that matter.

Failure policy. Auditing must never break the operation it is recording. Every
function catches its own exceptions and logs them; a database outage degrades
the audit trail without stopping a password reset that is already underway.
"""

from __future__ import annotations

import socket
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from loguru import logger
from sqlalchemy import select

from App.db.connection import SessionLocal
from App.db.models.app_users import AppUser
from App.db.models.operation_requests import (
    STATUS_AWAITING_APPROVAL,
    STATUS_FAILED,
    STATUS_RECEIVED,
    STATUS_REJECTED,
    STATUS_SUCCEEDED,
    OperationRequest,
)
from App.db.models.operation_executions import (
    EXECUTION_FAILED,
    EXECUTION_SUCCEEDED,
    OperationExecution,
)
from App.db.models.operations import Operation

# Namespace used to derive a stable UUID from the application's readable
# request ID. Any fixed UUID works; what matters is that it never changes, so
# "ui_9f29c7fc" always maps to the same row.
REQUEST_ID_NAMESPACE = uuid.UUID("6f9619ff-8b86-d011-b42d-00c04fc964ff")


def _optional_uuid(value: Any) -> Optional[uuid.UUID]:
    """Convert a UUID-like value to UUID, returning None when invalid."""
    if not value:
        return None

    try:
        return uuid.UUID(str(value))
    except (ValueError, AttributeError, TypeError):
        return None


def _resolve_requester_id(session, requester: Optional[str]) -> Optional[uuid.UUID]:
    """Resolve a UUID, UPN, or Windows identity to an app user UUID."""
    direct_id = _optional_uuid(requester)
    if direct_id is not None:
        return direct_id

    if not requester:
        return None

    identity = str(requester).strip().casefold()
    username = identity.rsplit("\\", maxsplit=1)[-1]

    users = session.execute(
        select(AppUser).where(AppUser.is_active.is_(True))
    ).scalars()
    for user in users:
        user_upn = user.user_principal_name.casefold()
        user_local_part = user_upn.split("@", maxsplit=1)[0]
        if user_upn == username or user_local_part == username:
            return user.user_id

    return None


def to_request_uuid(request_id: str) -> uuid.UUID:
    """
    Convert the application's request ID into the table's UUID primary key.

    operation_requests.request_id is a UUID, but the application generates
    readable IDs such as "ui_9f29c7fc" that appear in the log file. uuid5
    derives a UUID deterministically from that string, so the readable ID and
    the stored row stay tied together without needing a second column.

    A value that is already a UUID is used unchanged.

    Args:
        request_id: The application request ID.

    Returns:
        The UUID to use as the primary key.
    """
    try:
        return uuid.UUID(str(request_id))
    except (ValueError, AttributeError, TypeError):
        return uuid.uuid5(REQUEST_ID_NAMESPACE, str(request_id))


# The catalog entry each intent corresponds to.
#
# These values mirror App/db/seed_operations.py. Keeping them here as well
# means the catalog fills itself on first use, so operations is populated by
# running a query rather than only by running the seeder.
OPERATION_CATALOG = {
    "get_user_details": {
        "operation_code": "GET_USER_DETAILS",
        "operation_name": "Get User Details",
        "tool_name": "GET_USER_DETAILS",
        "risk_level": "LOW",
        "requires_approval": False,
    },
    "password_reset": {
        "operation_code": "RESET_PASSWORD",
        "operation_name": "Reset Password",
        "tool_name": "RESET_PASSWORD",
        "risk_level": "HIGH",
        "requires_approval": True,
    },
    "account_unlock": {
        "operation_code": "UNLOCK_USER",
        "operation_name": "Unlock User",
        "tool_name": "UNLOCK_ACCOUNT",
        "risk_level": "MEDIUM",
        "requires_approval": False,
    },
    "failed_login_investigation": {
        "operation_code": "FAILED_LOGIN_INVESTIGATION",
        "operation_name": "Lockout / Failed Login Investigation",
        "tool_name": "INVESTIGATE_FAILED_LOGIN",
        "risk_level": "LOW",
        "requires_approval": False,
    },
    "grant_access": {
        "operation_code": "ADD_USER_TO_GROUP",
        "operation_name": "Add User To Group",
        "tool_name": "MANAGE_ACCESS",
        "risk_level": "HIGH",
        "requires_approval": False,
    },
    "revoke_access": {
        "operation_code": "REMOVE_USER_FROM_GROUP",
        "operation_name": "Remove User From Group",
        "tool_name": "MANAGE_ACCESS",
        "risk_level": "HIGH",
        "requires_approval": True,
    },
}

# Backend name from the tool result, mapped to the execution_type the design
# document defines.
BACKEND_TO_EXECUTION_TYPE = {
    "api": "API",
    "script": "SCRIPT",
    "job": "JOB",
}


def _as_int(value: Any) -> Optional[int]:
    """
    Coerce a value to int, returning None when it is absent or not numeric.

    Args:
        value: Any value from a tool result.

    Returns:
        The integer, or None.
    """
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _error_detail(exc: Exception) -> str:
    """
    Return the database's own message for a failed audit write.

    Logging only the exception class name says a write failed but not why,
    which turns a one-line schema mismatch into a guessing game. Only the first
    line is kept, which is where PostgreSQL puts "column ... does not exist",
    and the SQL and its bound parameters are left out.

    Args:
        exc: The exception raised by SQLAlchemy.

    Returns:
        A short description, safe to log.
    """
    original = getattr(exc, "orig", exc)
    first_line = str(original).strip().splitlines()[0] if str(original).strip() else ""
    return first_line[:200] or type(exc).__name__


def mask_identifier(value: str) -> str:
    """
    Mask a user principal name for storage and dashboards.

    Section 7 asks for masked identifiers where the full value is not needed.
    The domain is kept because it carries no personal information and makes a
    row far easier to interpret; the local part is reduced to its first two
    characters.

        amit.bhagat@coforge.com  ->  am*********@coforge.com

    Args:
        value: The identifier to mask.

    Returns:
        The masked form, or an empty string when there was nothing to mask.
    """
    if not value:
        return ""

    text = str(value).strip()

    if "@" not in text:
        return text[:2] + "*" * max(len(text) - 2, 0)

    local, domain = text.split("@", 1)
    if len(local) <= 2:
        return f"{local}@{domain}"

    return f"{local[:2]}{'*' * (len(local) - 2)}@{domain}"


def sanitize_parameters(metadata: Dict[str, Any]) -> Dict[str, Any]:
    """
    Reduce extracted metadata to the fields that are safe to store.

    An allowlist rather than a blocklist, so a field added to the metadata in
    future is withheld by default instead of being written to the audit table
    until someone notices.

    Args:
        metadata: The extracted metadata from the agent.

    Returns:
        A dict containing only the approved keys that had values.
    """
    approved = ("username", "email", "user_id", "employee_number", "group_name")

    return {
        key: str(metadata.get(key))
        for key in approved
        if metadata and metadata.get(key)
    }


def ensure_operation_id(
    session,
    intent: Optional[str],
    execution_type: str = "API",
) -> Optional[uuid.UUID]:
    """
    Find the catalog operation for an intent, creating it if it is missing.

    This is what links operation_requests to operations. The row is created on
    first use rather than requiring the seeder to have been run, so both tables
    fill up from running a query.

    Only intents listed in OPERATION_CATALOG can be created. An intent the
    agent invented, or one refused by the guardrails, returns None: the catalog
    is the list of operations the agent is permitted to select, so it must not
    grow to fit whatever was asked for.

    An existing row is never overwritten. risk_level and requires_approval are
    governance decisions, and a running query is not the place to change them.

    Args:
        session: An open SQLAlchemy session.
        intent: The agent's resolved intent.
        execution_type: API, SCRIPT or JOB, from the backend that ran.

    Returns:
        The operation_id, or None when the intent is not in the catalog.
    """
    entry = OPERATION_CATALOG.get((intent or "").strip().lower())

    if not entry:
        return None

    statement = select(Operation).where(
        Operation.operation_code == entry["operation_code"]
    )
    operation = session.execute(statement).scalars().first()

    if operation is not None:
        return operation.operation_id if operation.is_active else None

    operation = Operation(
        operation_code=entry["operation_code"],
        operation_name=entry["operation_name"],
        execution_type=execution_type,
        tool_name=entry["tool_name"],
        script_name=None,
        risk_level=entry["risk_level"],
        requires_approval=entry["requires_approval"],
        is_active=True,
    )
    session.add(operation)

    try:
        session.flush()
    except Exception:
        # Another request created the same row first. Roll back this insert and
        # take theirs, rather than failing the audit write over a race.
        session.rollback()
        operation = session.execute(statement).scalars().first()
        return operation.operation_id if operation else None

    logger.info(
        "AUDIT_OPERATION_REGISTERED | operation_code={} | execution_type={} | "
        "risk_level={} | requires_approval={}",
        entry["operation_code"],
        execution_type,
        entry["risk_level"],
        entry["requires_approval"],
    )

    return operation.operation_id


def summarize_result(response: Dict[str, Any]) -> str:
    """
    Build a short, sanitized description of what an execution produced.

    The response payload itself is never stored: on a password reset it can
    carry the temporary password. Only the message line and the field names
    are kept.

    Args:
        response: The flow response.

    Returns:
        A string safe to write to result_summary.
    """
    message = str(response.get("message") or "").strip()

    result = (response.get("tool_result") or {}).get("result") or {}
    fields = sorted(result.keys()) if isinstance(result, dict) else []

    if fields:
        return f"{message[:400]} | fields={','.join(fields)[:300]}"

    return message[:400]


def record_execution(
    request_id: str,
    response: Dict[str, Any],
    started_at: Optional[datetime] = None,
    finished_at: Optional[datetime] = None,
) -> None:
    """
    Record one execution attempt in operation_executions.

    Called only when the flow actually reached a tool. A guardrail block or a
    pending confirmation produces no row here, because nothing was attempted;
    that outcome lives in operation_requests instead.

    Retries append rather than overwrite. The retry_count is derived from the
    number of rows already present for this request, so the history of a failed
    first attempt survives a successful second one.

    Args:
        request_id: The application request ID.
        response: The flow response, already through the output guardrails.
        started_at: When execution began.
        finished_at: When execution ended.
    """
    response = response or {}

    tool_result = response.get("tool_result") or {}

    # Nothing ran: no execution row.
    if not tool_result:
        return

    if response.get("confirmation_required") or response.get("guardrail_blocked"):
        return

    result = tool_result.get("result") or {}
    result = result if isinstance(result, dict) else {}

    started_at = started_at or datetime.now(timezone.utc)
    finished_at = finished_at or datetime.now(timezone.utc)
    duration_ms = int((finished_at - started_at).total_seconds() * 1000)

    backend = str(result.get("backend", "")).lower()
    succeeded = bool(response.get("success"))

    try:
        with SessionLocal() as session:
            row_key = to_request_uuid(request_id)

            # Count existing attempts so a retry is numbered rather than
            # replacing what came before.
            existing = (
                session.query(OperationExecution)
                .filter(OperationExecution.request_id == row_key)
                .count()
            )

            execution = OperationExecution(
                execution_id=uuid.uuid4(),
                request_id=row_key,
                execution_type=BACKEND_TO_EXECUTION_TYPE.get(backend, "API"),
                executor_name=(
                    tool_result.get("tool")
                    or tool_result.get("mcp_tool")
                    or response.get("intent")
                ),
                executor_version=str(result.get("tool_version") or "") or None,
                executor_host=socket.gethostname()[:255],
                started_at=started_at,
                finished_at=finished_at,
                execution_status=(
                    EXECUTION_SUCCEEDED if succeeded else EXECUTION_FAILED
                ),
                http_status_code=_as_int(result.get("status_code")),
                process_exit_code=_as_int(result.get("exit_code")),
                external_reference_id=(
                    result.get("request_id")
                    or response.get("correlation_id")
                    or None
                ),
                duration_ms=duration_ms,
                result_summary=summarize_result(response) or None,
                error_code=(str(result.get("error_code") or "") or None),
                error_message=(
                    str(response.get("error") or result.get("error") or "")[:2000]
                    or None
                ),
                retry_count=existing,
            )

            session.add(execution)
            session.commit()

            logger.info(
                "AUDIT_EXECUTION_RECORDED | request_id={} | execution_id={} | "
                "type={} | executor={} | status={} | duration_ms={} | attempt={}",
                request_id,
                execution.execution_id,
                execution.execution_type,
                execution.executor_name or "unknown",
                execution.execution_status,
                duration_ms,
                existing + 1,
            )

    except Exception as exc:
        logger.error(
            "AUDIT_EXECUTION_FAILED | request_id={} | error_type={} | detail={}",
            request_id,
            type(exc).__name__,
            _error_detail(exc),
        )


def open_request(
    request_id: str,
    user_query: str,
    requested_by: Optional[str] = None,
    source_channel: str = "WEB",
) -> None:
    """
    Record a request as soon as it arrives, before anything is decided.

    Args:
        request_id: The correlation ID, shared with the log file.
        user_query: The user's original text.
        requested_by: The app_users user_id of the signed-in person, if known.
        source_channel: WEB, API, TEAMS or another channel.
    """
    try:
        with SessionLocal() as session:
            row = OperationRequest(
                request_id=to_request_uuid(request_id),
                requested_by=_resolve_requester_id(session, requested_by),
                source_channel=source_channel,
                original_request=(user_query or "")[:4000],
                status=STATUS_RECEIVED,
            )
            session.add(row)
            session.commit()

        logger.info(
            "AUDIT_REQUEST_OPENED | request_id={} | row_uuid={} | status={} | requested_by={}",
            request_id,
            to_request_uuid(request_id),
            STATUS_RECEIVED,
            requested_by or "unknown",
        )

    except Exception as exc:
        # Never let auditing break the operation it is recording.
        logger.error(
            "AUDIT_REQUEST_OPEN_FAILED | request_id={} | error_type={} | detail={}",
            request_id,
            type(exc).__name__,
            _error_detail(exc),
        )


def get_user_request_history(
    user_id: str,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Return recent password-safe requests submitted by one app user."""

    requester_id = _optional_uuid(user_id)
    if requester_id is None:
        return []

    try:
        with SessionLocal() as session:
            statement = (
                select(OperationRequest, Operation.operation_name)
                .outerjoin(
                    Operation,
                    Operation.operation_id == OperationRequest.operation_id,
                )
                .where(OperationRequest.requested_by == requester_id)
                .order_by(OperationRequest.requested_at.desc())
                .limit(max(1, min(int(limit), 100)))
            )
            rows = session.execute(statement).all()

        return [
            {
                "request_id": str(request.request_id),
                "request": request.original_request or "",
                "operation": operation_name or "Identity request",
                "target": request.target_reference or "",
                "status": request.status,
                "requested_at": request.requested_at,
            }
            for request, operation_name in rows
        ]
    except Exception as exc:
        logger.error(
            "AUDIT_REQUEST_HISTORY_FAILED | user_id={} | error_type={} | detail={}",
            requester_id,
            type(exc).__name__,
            _error_detail(exc),
        )
        return []


def status_for(response: Dict[str, Any]) -> str:
    """
    Map a flow response to a request lifecycle status.

    Args:
        response: The response dict returned by the flow.

    Returns:
        One of the statuses defined in the design document.
    """
    if response.get("confirmation_required"):
        return STATUS_AWAITING_APPROVAL

    if response.get("guardrail_blocked"):
        return STATUS_REJECTED

    return STATUS_SUCCEEDED if response.get("success") else STATUS_FAILED


def close_request(
    request_id: str,
    response: Dict[str, Any],
    started_at: Optional[datetime] = None,
    finished_at: Optional[datetime] = None,
) -> None:
    """
    Update a request with everything the flow decided, and record the attempt.

    Fills in the operation, the target, the confidence and the final status.
    If the opening row is missing, because the database was unreachable at the
    time, one is created here so the request is still recorded.

    Both tables are written: operation_requests gets the final lifecycle
    status, and operation_executions gets a row when a tool actually ran.

    Args:
        request_id: The correlation ID.
        response: The response dict returned by the flow.
        started_at: When execution began, for the execution row.
        finished_at: When execution ended, for the execution row.
    """
    response = response or {}

    try:
        with SessionLocal() as session:
            row_key = to_request_uuid(request_id)
            row = session.get(OperationRequest, row_key)

            if row is None:
                row = OperationRequest(
                    request_id=row_key,
                    original_request=(response.get("user_input") or "")[:4000],
                    status=STATUS_RECEIVED,
                )
                session.add(row)

            metadata = response.get("metadata") or {}
            target = metadata.get("email") or metadata.get("username") or ""

            # The backend that actually ran decides the execution type recorded
            # against a newly created catalog entry.
            backend = str(
                (response.get("tool_result") or {}).get("result", {}).get("backend", "")
            ).lower()

            row.operation_id = ensure_operation_id(
                session,
                response.get("intent"),
                BACKEND_TO_EXECUTION_TYPE.get(backend, "API"),
            )
            row.target_type = "USER" if target else None
            row.target_reference = mask_identifier(target) or None
            row.request_parameters = sanitize_parameters(metadata) or None

            confidence = response.get("confidence")
            if isinstance(confidence, (int, float)):
                row.intent_confidence = round(float(confidence), 4)

            # The tool result carries the directory's own object ID, which is
            # stable even when a UPN is renamed.
            tool_result = response.get("tool_result") or {}
            result = tool_result.get("result") or {}
            if isinstance(result, dict):
                row.target_object_id = _optional_uuid(
                    result.get("id") or result.get("user_id")
                )

            row.status = status_for(response)
            row.completed_at = datetime.now(timezone.utc)

            session.commit()

            # The guardrail verdict has no column in the existing table, so it
            # is recorded in the log line rather than invented as a column.
            logger.info(
                "AUDIT_REQUEST_CLOSED | request_id={} | status={} | "
                "operation_id={} | target={} | confidence={} | guardrail={}",
                request_id,
                row.status,
                row.operation_id or "unresolved",
                row.target_reference or "none",
                row.intent_confidence if row.intent_confidence is not None else "none",
                response.get("guardrail_action") or "none",
            )

    except Exception as exc:
        logger.error(
            "AUDIT_REQUEST_CLOSE_FAILED | request_id={} | error_type={} | detail={}",
            request_id,
            type(exc).__name__,
            _error_detail(exc),
        )

    # Outside the block above, so the execution row is still written even when
    # updating the request row failed. The two tables answer different
    # questions and one failing should not silently lose the other.
    record_execution(request_id, response, started_at, finished_at)
