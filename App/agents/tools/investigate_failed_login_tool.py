from App.agents.tools.common import placeholder
from App.schemas.models import ToolName,ToolRequest,ToolResult
def investigate_failed_login_tool(request:ToolRequest)->ToolResult:
    return placeholder(request,ToolName.INVESTIGATE_FAILED_LOGIN,'Failed-login investigation tool called; data-source integration pending.')
