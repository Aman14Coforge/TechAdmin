from __future__ import annotations
from mcp.server import MCPServer
from App.tools.identity.manage_access import AccessManagementTool
from App.workflow.state import IdentityMetadata, IntentType, ToolRequest

mcp = MCPServer("techadmin-access-management")

@mcp.tool()
def manage_access(request_id: str, correlation_id: str, action: str, group_name: str, username: str | None = None, email: str | None = None, user_id: str | None = None, employee_number: str | None = None, username_source: str | None = None) -> dict:
    """Grant or revoke user access using the configured identity integration."""
    action = action.strip().lower()
    if action not in {"grant", "revoke"}:
        raise ValueError("action must be 'grant' or 'revoke'.")
    intent = IntentType.GRANT_ACCESS if action == "grant" else IntentType.REVOKE_ACCESS
    request = ToolRequest(request_id=request_id, correlation_id=correlation_id, intent=intent, metadata=IdentityMetadata(username=username, email=email, user_id=user_id, employee_number=employee_number, group_name=group_name, username_source=username_source))
    return AccessManagementTool().execute(request).model_dump(mode="json")

if __name__ == "__main__":
    mcp.run()
