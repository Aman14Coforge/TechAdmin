"""
Get User Details MCP Server

Purpose:
    Expose the existing GetUserDetailsTool through MCP.

Transport:
    stdio

Tool exposed:
    get_user_details
"""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv
from loguru import logger
from mcp.server import MCPServer

from App.tools.identity.get_user_details import (
    GetUserDetailsTool,
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
    "techadmin-get-user-details",
    instructions=(
        "Retrieve identity details through the configured "
        "Microsoft Graph integration."
    ),
)


@mcp.tool()
def get_user_details(
    request_id: str,
    correlation_id: str,
    username: str | None = None,
    email: str | None = None,
    user_id: str | None = None,
    employee_number: str | None = None,
    username_source: str | None = None,
) -> dict:
    """
    Retrieve user details through Microsoft Graph.
    """

    logger.info(
        "MCP_TOOL_RECEIVED | "
        "server=get_user_details | "
        "tool=get_user_details | "
        "request_id={} | correlation_id={}",
        request_id,
        correlation_id,
    )

    tool_request = ToolRequest(
        request_id=request_id,
        correlation_id=correlation_id,
        intent=IntentType.GET_USER_DETAILS,
        metadata=IdentityMetadata(
            username=username,
            email=email,
            user_id=user_id,
            employee_number=employee_number,
            username_source=username_source,
        ),
    )

    tool = GetUserDetailsTool()

    result = tool.execute(
        tool_request
    )

    logger.info(
        "MCP_TOOL_RETURNING | "
        "server=get_user_details | "
        "tool=get_user_details | "
        "status={} | operation_id={}",
        result.status.value,
        result.operation_id,
    )

    return result.model_dump(
        mode="json"
    )


if __name__ == "__main__":
    mcp.run()