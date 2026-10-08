from __future__ import annotations
from App.services.patch.service import PatchService
from App.workflow.state import AgentExecutionResult,IntentType,MetadataValidationResult,PatchMetadata,ToolName,ToolResult,ToolStatus
class PatchAgent:
 def __init__(self):self.service=PatchService()
 def execute(self,operation:IntentType,metadata:PatchMetadata,request_id:str,correlation_id:str)->AgentExecutionResult:
  missing=[]
  if operation is IntentType.PATCH_TICKET and not metadata.device_name:missing=["device_name"]
  valid=not missing;validation=MetadataValidationResult(is_valid=valid,missing_fields=missing,message="Patch metadata valid" if valid else "Device name is required")
  if not valid:return AgentExecutionResult(success=False,intent=operation,selected_agent="patch_agent",metadata=metadata,validation=validation,clarification_required=True,clarification_question="Which device should the patch ticket be raised for?",message=validation.message)
  try:
   if operation is IntentType.PATCH_REPORT:result=self.service.report(metadata.as_of_date,metadata.device_name,metadata.minimum_days);tool=ToolName.PATCH_REPORT
   elif operation is IntentType.PATCH_SCAN:result=self.service.scan();tool=ToolName.PATCH_SCAN
   elif operation is IntentType.PATCH_TICKET:
    if not metadata.approval_granted:return AgentExecutionResult(success=False,intent=operation,selected_agent="patch_agent",selected_tool=ToolName.PATCH_TICKET,metadata=metadata,validation=validation,clarification_required=False,message="Confirmation is required before raising the ticket.",error="confirmation_required")
    result=self.service.raise_ticket(metadata.device_name,metadata.ticket_reason);tool=ToolName.PATCH_TICKET
   else:raise ValueError("Unsupported patch intent")
   tr=ToolResult(success=True,tool_name=tool,status=ToolStatus.COMPLETED,message="Patch operation completed.",result=result)
   return AgentExecutionResult(success=True,intent=operation,selected_agent="patch_agent",selected_tool=tool,metadata=metadata,validation=validation,tool_result=tr,message=tr.message)
  except Exception as e:return AgentExecutionResult(success=False,intent=operation,selected_agent="patch_agent",metadata=metadata,validation=validation,message="Patch Agent execution failed.",error=type(e).__name__)
