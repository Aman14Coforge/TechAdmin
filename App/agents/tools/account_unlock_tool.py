from App.agents.tools.common import placeholder
from App.schemas.models import ToolName,ToolRequest,ToolResult
def unlock_account_tool(request:ToolRequest)->ToolResult:
    return placeholder(request,ToolName.UNLOCK_ACCOUNT,'Account unlock tool called; API integration pending.')
