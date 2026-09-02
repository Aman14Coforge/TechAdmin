"""
Password Reset MCP Server

Purpose:
    Expose the existing GraphAPIPasswordResetTool through MCP.

Transport:
    stdio

Tool exposed:
    reset_password
"""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv
from loguru import logger
from mcp.server import MCPServer

from App.tools.identity.reset_password import (
    GraphAPIPasswordResetTool,
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
    "techadmin-password-reset",
    instructions=(
        "Reset passwords through the configured "
        "Microsoft Graph integration."
    ),
)


@mcp.tool()
def reset_password(
    request_id: str,
    correlation_id: str,
    username: str | None = None,
    email: str | None = None,
    user_id: str | None = None,
    employee_number: str | None = None,
    username_source: str | None = None,
) -> dict:
    """
    Reset a user's password through Microsoft Graph.

    A username, email, or Graph user ID must identify the target.
    Temporary credentials are never returned through the MCP result.
    """

    logger.info(
        "MCP_TOOL_RECEIVED | "
        "server=password_reset | "
        "tool=reset_password | "
        "request_id={} | correlation_id={}",
        request_id,
        correlation_id,
    )

    tool_request = ToolRequest(
        request_id=request_id,
        correlation_id=correlation_id,
        intent=IntentType.PASSWORD_RESET,
        metadata=IdentityMetadata(
            username=username,
            email=email,
            user_id=user_id,
            employee_number=employee_number,
            username_source=username_source,
        ),
    )

    tool = GraphAPIPasswordResetTool()

    result = tool.execute(
        tool_request
    )

    logger.info(
        "MCP_TOOL_RETURNING | "
        "server=password_reset | "
        "tool=reset_password | "
        "status={} | operation_id={}",
        result.status.value,
        result.operation_id,
    )

    return result.model_dump(
        mode="json"
    )


if __name__ == "__main__":
    mcp.run()