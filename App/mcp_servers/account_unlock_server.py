from __future__ import annotations
from mcp.server import MCPServer
from App.tools.identity.unlock_account import AccountUnlockTool
from App.workflow.state import IdentityMetadata, IntentType, ToolRequest
mcp = MCPServer("techadmin-account-unlock")
@mcp.tool()
def unlock_account(request_id: str, correlation_id: str, username: str) -> dict:
    """Unlock an Active Directory user account using the approved script."""
    request = ToolRequest(request_id=request_id, correlation_id=correlation_id, intent=IntentType.ACCOUNT_UNLOCK, metadata=IdentityMetadata(username=username))
    return AccountUnlockTool().execute(request).model_dump(mode="json")
if __name__ == "__main__":
    mcp.run()
