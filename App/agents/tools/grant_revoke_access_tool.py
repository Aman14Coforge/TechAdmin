from App.agents.tools.common import placeholder
from App.schemas.models import ToolName,ToolRequest,ToolResult
def grant_revoke_access_tool(request:ToolRequest)->ToolResult:
    return placeholder(request,ToolName.GRANT_REVOKE_ACCESS,'Grant/revoke access tool called; API integration pending.')
