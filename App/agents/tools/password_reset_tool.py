from App.agents.tools.common import placeholder
from App.schemas.models import ToolName,ToolRequest,ToolResult
def reset_password_tool(request:ToolRequest)->ToolResult:
    return placeholder(request,ToolName.RESET_PASSWORD,'Password reset tool called; API integration pending.')
