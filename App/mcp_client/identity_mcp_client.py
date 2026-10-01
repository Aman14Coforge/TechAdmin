from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

from mcp import Client
from mcp.client.stdio import StdioServerParameters
from pydantic import BaseModel, ConfigDict


class MCPToolCallResult(BaseModel):
    model_config = ConfigDict(
        extra="allow",
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
    SERVER_MODULES = {
        "password_reset": (
            "App.mcp_servers.password_reset_server"
        ),
        "get_user_details": (
            "App.mcp_servers.get_user_details_server"
        ),
        "get_computer_details": (
            "App.mcp_servers.get_computer_details_server"
        ),
        "account_unlock": (
            "App.mcp_servers.account_unlock_server"
        ),
        "grant_access": (
            "App.mcp_servers.access_management_server"
        ),
        "revoke_access": (
            "App.mcp_servers.access_management_server"
        ),
        "failed_login_investigation": (
            "App.mcp_servers.failed_login_server"
        ),
        "create_user": (
            "App.mcp_servers.directory_operations_server"
        ),
        "delete_user": (
            "App.mcp_servers.directory_operations_server"
        ),
        "create_group": (
            "App.mcp_servers.directory_operations_server"
        ),
        "create_vm": (
            "App.mcp_servers.directory_operations_server"
        ),
    }

    TOOL_NAMES = {
        "password_reset": "reset_password",
        "get_user_details": "get_user_details",
        "get_computer_details": "get_computer_details",
        "account_unlock": "unlock_account",
        "grant_access": "manage_access",
        "revoke_access": "manage_access",
        "failed_login_investigation": (
            "investigate_failed_login"
        ),
        "create_user": "create_user",
        "delete_user": "delete_user",
        "create_group": "create_group",
        "create_vm": "create_vm",
    }

    def __init__(
        self,
        project_root: Path | None = None,
    ) -> None:
        self.project_root = (
            project_root
            or Path(__file__).resolve().parents[2]
        ).resolve()

    async def call_tool(
        self,
        *,
        operation: str,
        arguments: dict[str, Any],
    ) -> MCPToolCallResult:
        normalized_operation = (
            operation.strip().casefold()
            if isinstance(operation, str)
            else ""
        )

        module = self.SERVER_MODULES.get(
            normalized_operation
        )

        tool_name = self.TOOL_NAMES.get(
            normalized_operation
        )

        if not module or not tool_name:
            missing_parts: list[str] = []

            if not module:
                missing_parts.append(
                    "server module"
                )

            if not tool_name:
                missing_parts.append(
                    "MCP tool name"
                )

            raise ValueError(
                "Incomplete MCP registration for "
                f"'{normalized_operation}'. Missing: "
                f"{', '.join(missing_parts)}"
            )

        parameters = StdioServerParameters(
            command=sys.executable,
            args=[
                "-m",
                module,
            ],
            cwd=str(
                self.project_root
            ),
            env=dict(
                os.environ
            ),
        )

        async with Client(
            parameters
        ) as client:
            response = await client.call_tool(
                tool_name,
                arguments,
            )

            structured = getattr(
                response,
                "structured_content",
                None,
            )

            if isinstance(
                structured,
                dict,
            ):
                return MCPToolCallResult.model_validate(
                    structured
                )

            text = "".join(
                getattr(
                    block,
                    "text",
                    "",
                )
                for block in getattr(
                    response,
                    "content",
                    [],
                )
            ).strip()

            if not text:
                raise ValueError(
                    "The MCP server returned no "
                    "structured or textual response."
                )

            parsed = json.loads(
                text
            )

            return MCPToolCallResult.model_validate(
                parsed
            )