import logging
from App.schemas.models import ToolName,ToolRequest,ToolResult,ToolStatus
logger=logging.getLogger('techadmin.tools')
def placeholder(req:ToolRequest,name:ToolName,message:str)->ToolResult:
    logger.info('TOOL_CALL tool=%s intent=%s correlation_id=%s username=%s email=%s employee_id=%s group_name=%s time_window=%s',name.value,req.intent.value,req.correlation_id,req.fields.username,req.fields.email,req.fields.employee_id,req.fields.group_name,req.fields.time_window)
    # TODO: call approved enterprise API here and map its response to ToolResult.
    result=ToolResult(tool=name,status=ToolStatus.NOT_IMPLEMENTED,message=message)
    logger.info('TOOL_RESULT tool=%s status=%s operation_id=%s api_integration_pending=%s',result.tool.value,result.status.value,result.operation_id,result.api_integration_pending)
    return result
