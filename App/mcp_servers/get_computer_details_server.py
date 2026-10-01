"""MCP-facing server adapter for read-only AD computer lookup."""
from __future__ import annotations

from mcp.server import MCPServer

from App.tools.get_computer_details import GetComputerDetailsTool
from App.workflow.state import ExecutionBackend, IdentityMetadata

mcp = MCPServer("techadmin-get-computer-details")


@mcp.tool()
def get_computer_details(
    request_id: str,
    correlation_id: str,
    execution_backend: str,
    hostname: str | None = None,
) -> dict:
    """Get Active Directory computer details through the approved PowerShell script."""
    metadata = IdentityMetadata(
        hostname=hostname,
        execution_backend=ExecutionBackend(execution_backend),
    )
    return GetComputerDetailsTool().execute(
        metadata=metadata,
        request_id=request_id,
        correlation_id=correlation_id,
    ).model_dump(mode="json")


if __name__ == "__main__":
    mcp.run()
