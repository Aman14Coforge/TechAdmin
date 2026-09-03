from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

from loguru import logger
from mcp import Client
from mcp.client.stdio import StdioServerParameters
from pydantic import BaseModel, ConfigDict


class MCPToolCallResult(BaseModel):
    model_config = ConfigDict(extra="allow", str_strip_whitespace=True)

    success: bool
    tool_name: str
    status: str
    operation_id: str | None = None
    message: str
    result: dict[str, Any] | None = None
    error: str | None = None
    api_integration_pending: bool = False


class IdentityMCPClient:
    SERVER_MODULES = {
        "password_reset": "App.mcp_servers.password_reset_server",
        "get_user_details": "App.mcp_servers.get_user_details_server",
        "account_unlock": "App.mcp_servers.account_unlock_server",
        "grant_access": "App.mcp_servers.access_management_server",
        "revoke_access": "App.mcp_servers.access_management_server",
        "failed_login_investigation": "App.mcp_servers.failed_login_server",
    }

    TOOL_NAMES = {
        "password_reset": "reset_password",
        "get_user_details": "get_user_details",
        "account_unlock": "unlock_account",
        "grant_access": "manage_access",
        "revoke_access": "manage_access",
        "failed_login_investigation": "investigate_failed_login",
    }

    def __init__(self, project_root: Path | None = None) -> None:
        self.project_root = project_root or Path(__file__).resolve().parents[2]

    async def call_tool(self, *, operation: str, arguments: dict[str, Any]) -> MCPToolCallResult:
        server_module = self.SERVER_MODULES.get(operation)
        tool_name = self.TOOL_NAMES.get(operation)
        if not server_module or not tool_name:
            raise ValueError(f"No MCP registration for operation '{operation}'.")

        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", server_module],
            cwd=str(self.project_root),
            env=dict(os.environ),
        )

        logger.info(
            "MCP_SERVER_STARTING | operation={} | server_module={} | mcp_tool={}",
            operation,
            server_module,
            tool_name,
        )

        async with Client(params) as client:
            listed = await client.list_tools()
            available = {item.name for item in listed.tools}
            if tool_name not in available:
                raise RuntimeError(
                    f"MCP server '{server_module}' does not expose '{tool_name}'."
                )

            logger.info(
                "MCP_PROTOCOL_CALL | operation={} | server_module={} | mcp_tool={} | correlation_id={}",
                operation,
                server_module,
                tool_name,
                arguments.get("correlation_id"),
            )

            response = await client.call_tool(tool_name, arguments)
            parsed = self._parse_result(response)

            logger.info(
                "MCP_PROTOCOL_RESULT | operation={} | mcp_tool={} | status={} | success={} | operation_id={}",
                operation,
                tool_name,
                parsed.status,
                parsed.success,
                parsed.operation_id,
            )
            return parsed

    @staticmethod
    def _parse_result(call_result: Any) -> MCPToolCallResult:
        structured = getattr(call_result, "structured_content", None)
        if isinstance(structured, dict):
            return MCPToolCallResult.model_validate(structured)

        blocks = getattr(call_result, "content", None)
        text = "".join(
            getattr(block, "text", "")
            for block in (blocks or [])
            if isinstance(getattr(block, "text", None), str)
        ).strip()
        if not text:
            raise RuntimeError("MCP tool returned no structured or text content.")
        return MCPToolCallResult.model_validate(json.loads(text))
