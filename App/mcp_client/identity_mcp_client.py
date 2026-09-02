"""
Identity MCP Client

Purpose:
    Connect the Identity Agent to the appropriate Identity MCP server.

Transport:
    Local stdio transport.

Responsibilities:
    - Map an Identity intent to an MCP server.
    - Start only the required MCP server.
    - Verify that the expected MCP tool is exposed.
    - Call the MCP tool.
    - Parse and validate the MCP result.
    - Close the MCP connection and subprocess immediately after use.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

from loguru import logger
from mcp import Client
from mcp.client.stdio import (
    StdioServerParameters,
)
from pydantic import (
    BaseModel,
    ConfigDict,
)


class MCPToolCallResult(BaseModel):
    """
    Pydantic representation of an Identity MCP tool response.
    """

    model_config = ConfigDict(
        extra="allow",
        str_strip_whitespace=True,
    )

    success: bool
    tool_name: str
    status: str
    operation_id: str | None = None
    message: str
    result: dict[str, Any] | None = None
    error: str | None = None
    api_integration_pending: bool = False


class IdentityMCPClient:
    """
    MCP client used by IdentityAgent.

    The LLM never selects an MCP server or tool. The normalized intent
    is mapped deterministically through SERVER_MODULES and TOOL_NAMES.
    """

    SERVER_MODULES: dict[str, str] = {
        "password_reset":
            "App.mcp_servers.password_reset_server",

        "get_user_details":
            "App.mcp_servers.get_user_details_server",

        "account_unlock":
            "App.mcp_servers.account_unlock_server",

        "grant_access":
            "App.mcp_servers.access_management_server",

        "revoke_access":
            "App.mcp_servers.access_management_server",

        "failed_login_investigation":
            "App.mcp_servers.failed_login_server",
    }

    TOOL_NAMES: dict[str, str] = {
        "password_reset":
            "reset_password",

        "get_user_details":
            "get_user_details",

        "account_unlock":
            "unlock_account",

        "grant_access":
            "manage_access",

        "revoke_access":
            "manage_access",

        "failed_login_investigation":
            "investigate_failed_login",
    }

    def __init__(
        self,
        project_root: Path | None = None,
    ) -> None:
        self.project_root = (
            project_root
            or Path(__file__).resolve().parents[2]
        )

    async def call_tool(
        self,
        *,
        operation: str,
        arguments: dict[str, Any],
    ) -> MCPToolCallResult:
        """
        Start the selected MCP server and call its registered tool.

        The server subprocess is closed when the async context exits.
        """

        server_module = self.SERVER_MODULES.get(
            operation
        )

        mcp_tool_name = self.TOOL_NAMES.get(
            operation
        )

        if server_module is None:
            raise ValueError(
                f"No MCP server is registered for "
                f"operation '{operation}'."
            )

        if mcp_tool_name is None:
            raise ValueError(
                f"No MCP tool is registered for "
                f"operation '{operation}'."
            )

        logger.info(
            "MCP_SERVER_STARTING | "
            "operation={} | server_module={} | "
            "mcp_tool={}",
            operation,
            server_module,
            mcp_tool_name,
        )

        server_parameters = StdioServerParameters(
            command=sys.executable,
            args=[
                "-m",
                server_module,
            ],
            cwd=str(self.project_root),
            env=self._build_server_environment(),
        )

        async with Client(
            server_parameters
        ) as client:
            available_tools_result = (
                await client.list_tools()
            )

            available_tools = {
                tool.name
                for tool
                in available_tools_result.tools
            }

            logger.info(
                "MCP_TOOLS_DISCOVERED | "
                "server_module={} | tools={}",
                server_module,
                sorted(available_tools),
            )

            if mcp_tool_name not in available_tools:
                raise RuntimeError(
                    f"MCP server '{server_module}' "
                    f"does not expose expected tool "
                    f"'{mcp_tool_name}'."
                )

            logger.info(
                "MCP_PROTOCOL_CALL | "
                "operation={} | server_module={} | "
                "mcp_tool={} | correlation_id={}",
                operation,
                server_module,
                mcp_tool_name,
                arguments.get("correlation_id"),
            )

            raw_result = await client.call_tool(
                mcp_tool_name,
                arguments,
            )

            parsed_result = self._parse_call_result(
                raw_result
            )

            logger.info(
                "MCP_PROTOCOL_RESULT | "
                "operation={} | mcp_tool={} | "
                "status={} | success={} | "
                "operation_id={}",
                operation,
                mcp_tool_name,
                parsed_result.status,
                parsed_result.success,
                parsed_result.operation_id,
            )

            return parsed_result

    @staticmethod
    def _build_server_environment() -> dict[str, str]:
        """
        Pass the current process environment to the MCP subprocess.

        Microsoft Graph credentials remain environment variables. The
        values are never written to logs.
        """

        return {
            key: value
            for key, value in os.environ.items()
            if isinstance(value, str)
        }

    @classmethod
    def _parse_call_result(
        cls,
        call_result: Any,
    ) -> MCPToolCallResult:
        """
        Parse an MCP CallToolResult.

        Structured output is preferred. Text content is used only for
        compatibility when structured_content is unavailable.
        """

        structured_content = getattr(
            call_result,
            "structured_content",
            None,
        )

        if isinstance(
            structured_content,
            dict,
        ):
            return MCPToolCallResult.model_validate(
                structured_content
            )

        content_blocks = getattr(
            call_result,
            "content",
            None,
        )

        if not isinstance(
            content_blocks,
            list,
        ):
            raise RuntimeError(
                "MCP tool returned neither structured "
                "content nor readable text content."
            )

        text_parts: list[str] = []

        for content_block in content_blocks:
            text_value = getattr(
                content_block,
                "text",
                None,
            )

            if isinstance(
                text_value,
                str,
            ):
                text_parts.append(
                    text_value
                )

        combined_text = "".join(
            text_parts
        ).strip()

        if not combined_text:
            raise RuntimeError(
                "MCP tool returned an empty result."
            )

        try:
            parsed_json = json.loads(
                combined_text
            )

        except json.JSONDecodeError as exc:
            raise RuntimeError(
                "MCP tool returned text that was not "
                "valid JSON."
            ) from exc

        return MCPToolCallResult.model_validate(
            parsed_json
        )