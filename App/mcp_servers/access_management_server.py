from __future__ import annotations
from mcp.server import MCPServer
from App.tools.identity.manage_access import AccessManagementTool
from App.workflow.state import IdentityMetadata, IntentType, ToolRequest
mcp = MCPServer("techadmin-access-management")
@mcp.tool()
def manage_access(request_id: str, correlation_id: str, action: str, username: str, group_name: str, approval_granted: bool = False) -> dict:
    """Add or remove an Active Directory user from a group using approved scripts."""
    normalized = action.strip().lower()
    if normalized not in {"grant", "revoke"}:
        raise ValueError("action must be grant or revoke")
    intent = IntentType.GRANT_ACCESS if normalized == "grant" else IntentType.REVOKE_ACCESS
    request = ToolRequest(request_id=request_id, correlation_id=correlation_id, intent=intent, metadata=IdentityMetadata(username=username, group_name=group_name, approval_granted=approval_granted))
    return AccessManagementTool().execute(request).model_dump(mode="json")
if __name__ == "__main__":
    mcp.run()
