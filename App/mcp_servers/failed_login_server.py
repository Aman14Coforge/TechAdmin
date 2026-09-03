from __future__ import annotations
from mcp.server import MCPServer
from App.tools.identity.investigate_failed_login import FailedLoginInvestigationTool
from App.workflow.state import IdentityMetadata, IntentType, ToolRequest

mcp = MCPServer("techadmin-failed-login")

@mcp.tool()
def investigate_failed_login(request_id: str, correlation_id: str, username: str | None = None, email: str | None = None, user_id: str | None = None, employee_number: str | None = None, time_window: str | None = None, username_source: str | None = None) -> dict:
    """Investigate failed login events using the configured identity integration."""
    request = ToolRequest(request_id=request_id, correlation_id=correlation_id, intent=IntentType.FAILED_LOGIN_INVESTIGATION, metadata=IdentityMetadata(username=username, email=email, user_id=user_id, employee_number=employee_number, time_window=time_window, username_source=username_source))
    return FailedLoginInvestigationTool().execute(request).model_dump(mode="json")

if __name__ == "__main__":
    mcp.run()
