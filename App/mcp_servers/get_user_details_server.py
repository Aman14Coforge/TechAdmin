from __future__ import annotations
from mcp.server import MCPServer
from App.tools.identity.hybrid_identity import HybridGetUserDetailsTool
from App.workflow.state import ExecutionBackend,IdentityMetadata,IntentType,ToolRequest
mcp=MCPServer("techadmin-get-user-details")
@mcp.tool()
def get_user_details(request_id:str,correlation_id:str,execution_backend:str,username:str|None=None,email:str|None=None,user_id:str|None=None)->dict:
    """Get user details through Microsoft Graph API or approved PowerShell script."""
    req=ToolRequest(request_id=request_id,correlation_id=correlation_id,intent=IntentType.GET_USER_DETAILS,metadata=IdentityMetadata(username=username,email=email,user_id=user_id,execution_backend=ExecutionBackend(execution_backend)))
    return HybridGetUserDetailsTool().execute(req).model_dump(mode="json")
if __name__=="__main__":mcp.run()
