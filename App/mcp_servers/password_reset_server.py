from __future__ import annotations

from mcp.server import MCPServer

from App.tools.identity.hybrid_identity import (
    HybridPasswordResetTool,
)
from App.workflow.state import (
    ExecutionBackend,
    IdentityMetadata,
    IntentType,
    ToolRequest,
)


mcp = MCPServer("techadmin-password-reset")


@mcp.tool()
def reset_password(
    request_id: str,
    correlation_id: str,
    execution_backend: str,
    username: str | None = None,
    email: str | None = None,
    user_id: str | None = None,
    employee_number: str | None = None,
    approval_granted: bool = False,
) -> dict:
    """
    Verify identity and reset a password through Microsoft Graph API
    or the approved PowerShell script.

    Password reset requires:
    - complete company email address
    - employee ID
    - trusted approval
    """

    request = ToolRequest(
        request_id=request_id,
        correlation_id=correlation_id,
        intent=IntentType.PASSWORD_RESET,
        metadata=IdentityMetadata(
            username=username,
            email=email,
            user_id=user_id,
            employee_number=employee_number,
            execution_backend=ExecutionBackend(
                execution_backend
            ),
            approval_granted=approval_granted,
        ),
    )

    return (
        HybridPasswordResetTool()
        .execute(request)
        .model_dump(mode="json")
    )


if __name__ == "__main__":
    mcp.run()