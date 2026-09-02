"""
Access Management MCP Server

Purpose:
    Expose the existing AccessManagementTool through MCP.

Transport:
    stdio

Tool exposed:
    manage_access
"""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv
from loguru import logger
from mcp.server import MCPServer

from App.tools.identity.manage_access import (
    AccessManagementTool,
)
from App.workflow.state import (
    IdentityMetadata,
    IntentType,
    ToolRequest,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]

load_dotenv(
    PROJECT_ROOT / ".env"
)


mcp = MCPServer(
    "techadmin-access-management",
    instructions=(
        "Grant or revoke identity access through the "
        "configured access-management integration."
    ),
)


@mcp.tool()
def manage_access(
    request_id: str,
    correlation_id: str,
    action: str,
    group_name: str,
    username: str | None = None,
    email: str | None = None,
    user_id: str | None = None,
    employee_number: str | None = None,
    username_source: str | None = None,
) -> dict:
    """
    Grant or revoke access for an identity.

    action must be either grant or revoke.
    """

    normalized_action = action.strip().casefold()

    if normalized_action not in {
        "grant",
        "revoke",
    }:
        raise ValueError(
            "action must be either 'grant' or 'revoke'."
        )

    intent = (
        IntentType.GRANT_ACCESS
        if normalized_action == "grant"
        else IntentType.REVOKE_ACCESS
    )

    logger.info(
        "MCP_TOOL_RECEIVED | "
        "server=access_management | "
        "tool=manage_access | action={} | "
        "request_id={} | correlation_id={}",
        normalized_action,
        request_id,
        correlation_id,
    )

    tool_request = ToolRequest(
        request_id=request_id,
        correlation_id=correlation_id,
        intent=intent,
        metadata=IdentityMetadata(
            username=username,
            email=email,
            user_id=user_id,
            employee_number=employee_number,
            group_name=group_name,
            username_source=username_source,
        ),
    )

    tool = AccessManagementTool()

    result = tool.execute(
        tool_request
    )

    logger.info(
        "MCP_TOOL_RETURNING | "
        "server=access_management | "
        "tool=manage_access | action={} | "
        "status={} | operation_id={}",
        normalized_action,
        result.status.value,
        result.operation_id,
    )

    return result.model_dump(
        mode="json"
    )


if __name__ == "__main__":
    mcp.run()
