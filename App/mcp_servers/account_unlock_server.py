from __future__ import annotations
from mcp.server import MCPServer
from App.tools.identity.unlock_account import AccountUnlockTool
from App.workflow.state import IdentityMetadata, IntentType, ToolRequest

mcp = MCPServer("techadmin-account-unlock")

@mcp.tool()
def unlock_account(request_id: str, correlation_id: str, username: str | None = None, email: str | None = None, user_id: str | None = None, employee_number: str | None = None, username_source: str | None = None) -> dict:
    """Unlock a user account using the configured identity integration."""
    request = ToolRequest(request_id=request_id, correlation_id=correlation_id, intent=IntentType.ACCOUNT_UNLOCK, metadata=IdentityMetadata(username=username, email=email, user_id=user_id, employee_number=employee_number, username_source=username_source))
    return AccountUnlockTool().execute(request).model_dump(mode="json")

if __name__ == "__main__":
    mcp.run()
