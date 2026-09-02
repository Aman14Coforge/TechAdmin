"""
Failed Login Investigation MCP Server

Purpose:
    Expose the existing FailedLoginInvestigationTool through MCP.

Transport:
    stdio

Tool exposed:
    investigate_failed_login
"""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv
from loguru import logger
from mcp.server import MCPServer

from App.tools.identity.investigate_failed_login import (
    FailedLoginInvestigationTool,
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
    "techadmin-failed-login-investigation",
    instructions=(
        "Investigate failed logins and account lockouts "
        "through the configured identity data sources."
    ),
)


@mcp.tool()
def investigate_failed_login(
    request_id: str,
    correlation_id: str,
    username: str | None = None,
    email: str | None = None,
    user_id: str | None = None,
    employee_number: str | None = None,
    time_window: str | None = None,
    username_source: str | None = None,
) -> dict:
    """
    Investigate failed-login and account-lockout activity.
    """

    logger.info(
        "MCP_TOOL_RECEIVED | "
        "server=failed_login | "
        "tool=investigate_failed_login | "
        "request_id={} | correlation_id={}",
        request_id,
        correlation_id,
    )

    tool_request = ToolRequest(
        request_id=request_id,
        correlation_id=correlation_id,
        intent=(
            IntentType.FAILED_LOGIN_INVESTIGATION
        ),
        metadata=IdentityMetadata(
            username=username,
            email=email,
            user_id=user_id,
            employee_number=employee_number,
            time_window=time_window,
            username_source=username_source,
        ),
    )

    tool = FailedLoginInvestigationTool()

    result = tool.execute(
        tool_request
    )

    logger.info(
        "MCP_TOOL_RETURNING | "
        "server=failed_login | "
        "tool=investigate_failed_login | "
        "status={} | operation_id={}",
        result.status.value,
        result.operation_id,
    )

    return result.model_dump(
        mode="json"
    )


if __name__ == "__main__":
    mcp.run()