from __future__ import annotations
from mcp.server import MCPServer
from App.tools.identity.reset_password import GraphAPIPasswordResetTool
from App.workflow.state import IdentityMetadata, IntentType, ToolRequest

mcp = MCPServer("techadmin-password-reset")

@mcp.tool()
def reset_password(request_id: str, correlation_id: str, username: str | None = None, email: str | None = None, user_id: str | None = None, employee_number: str | None = None, username_source: str | None = None) -> dict:
    """Reset a user password using the configured Microsoft Graph integration."""
    request = ToolRequest(request_id=request_id, correlation_id=correlation_id, intent=IntentType.PASSWORD_RESET, metadata=IdentityMetadata(username=username, email=email, user_id=user_id, employee_number=employee_number, username_source=username_source))
    return GraphAPIPasswordResetTool().execute(request).model_dump(mode="json")

if __name__ == "__main__":
    mcp.run()
