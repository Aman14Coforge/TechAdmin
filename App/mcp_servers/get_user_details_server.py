from __future__ import annotations
from mcp.server import MCPServer
from App.tools.identity.get_user_details import GetUserDetailsTool
from App.workflow.state import IdentityMetadata, IntentType, ToolRequest

mcp = MCPServer("techadmin-get-user-details")

@mcp.tool()
def get_user_details(request_id: str, correlation_id: str, username: str | None = None, email: str | None = None, user_id: str | None = None, employee_number: str | None = None, username_source: str | None = None) -> dict:
    """Retrieve user details from the configured Microsoft Graph integration."""
    request = ToolRequest(request_id=request_id, correlation_id=correlation_id, intent=IntentType.GET_USER_DETAILS, metadata=IdentityMetadata(username=username, email=email, user_id=user_id, employee_number=employee_number, username_source=username_source))
    return GetUserDetailsTool().execute(request).model_dump(mode="json")

if __name__ == "__main__":
    mcp.run()
