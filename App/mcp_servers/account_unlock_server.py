"""
Account Unlock MCP Server

Purpose:
    Expose the existing AccountUnlockTool through MCP.

Transport:
    stdio

Tool exposed:
    unlock_account
"""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv
from loguru import logger
from mcp.server import MCPServer

from App.tools.identity.unlock_account import (
    AccountUnlockTool,
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
    "techadmin-account-unlock",
    instructions=(
        "Unlock identity accounts through the configured "
        "account-unlock integration."
    ),
)


@mcp.tool()
def unlock_account(
    request_id: str,
    correlation_id: str,
    username: str | None = None,
    email: str | None = None,
    user_id: str | None = None,
    employee_number: str | None = None,
    username_source: str | None = None,
) -> dict:
    """
    Unlock an identity account.
    """

    logger.info(
        "MCP_TOOL_RECEIVED | "
        "server=account_unlock | "
        "tool=unlock_account | "
        "request_id={} | correlation_id={}",
        request_id,
        correlation_id,
    )

    tool_request = ToolRequest(
        request_id=request_id,
        correlation_id=correlation_id,
        intent=IntentType.ACCOUNT_UNLOCK,
        metadata=IdentityMetadata(
            username=username,
            email=email,
            user_id=user_id,
            employee_number=employee_number,
            username_source=username_source,
        ),
    )

    tool = AccountUnlockTool()

    result = tool.execute(
        tool_request
    )

    logger.info(
        "MCP_TOOL_RETURNING | "
        "server=account_unlock | "
        "tool=unlock_account | "
        "status={} | operation_id={}",
        result.status.value,
        result.operation_id,
    )

    return result.model_dump(
        mode="json"
    )


if __name__ == "__main__":
    mcp.run()
