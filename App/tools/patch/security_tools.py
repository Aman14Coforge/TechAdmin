"""Patch tools using TechAdmin ToolRequest and ToolResult contracts."""
from __future__ import annotations
from datetime import date
from App.services.patch.analytics_service import PatchAnalyticsService
from App.services.patch.ticket_service import PatchTicketService
from App.workflow.state import IntentType,PatchMetadata,ToolName,ToolRequest,ToolResult,ToolStatus

class _Base:
    name:ToolName
    def result(self,success:bool,status:ToolStatus,message:str,*,result=None,error=None)->ToolResult:
        return ToolResult(success=success,tool_name=self.name,status=status,message=message,result=result,error=error,api_integration_pending=False)

class PatchDeviceReportTool(_Base):
    name=ToolName.PATCH_DEVICE_REPORT
    def execute(self,request:ToolRequest)->ToolResult:
        metadata=request.metadata
        if not isinstance(metadata,PatchMetadata) or not metadata.device_name:return self.result(False,ToolStatus.REJECTED,"A device name is required.",error="Missing device_name")
        try:return self.result(True,ToolStatus.COMPLETED,"Device intelligence report completed.",result=PatchAnalyticsService().device_report(metadata.device_name,report_date=metadata.report_date))
        except Exception as exc:return self.result(False,ToolStatus.FAILED,"Device intelligence report failed.",error=f"{type(exc).__name__}: {exc}")

class PatchFleetReportTool(_Base):
    name=ToolName.PATCH_FLEET_REPORT
    def execute(self,request:ToolRequest)->ToolResult:
        metadata=request.metadata
        if not isinstance(metadata,PatchMetadata):return self.result(False,ToolStatus.REJECTED,"Patch metadata is required.",error="Invalid metadata")
        try:return self.result(True,ToolStatus.COMPLETED,"Fleet intelligence report completed.",result=PatchAnalyticsService().fleet_report(report_date=metadata.report_date or metadata.as_of_date or date.today(),device_names=None))
        except Exception as exc:return self.result(False,ToolStatus.FAILED,"Fleet intelligence report failed.",error=f"{type(exc).__name__}: {exc}")

class PatchSelectedReportTool(_Base):
    name=ToolName.PATCH_SELECTED_REPORT
    def execute(self,request:ToolRequest)->ToolResult:
        metadata=request.metadata
        if not isinstance(metadata,PatchMetadata) or not metadata.device_names:return self.result(False,ToolStatus.REJECTED,"Select one or more devices.",error="Missing device_names")
        try:return self.result(True,ToolStatus.COMPLETED,"Selected-device intelligence report completed.",result=PatchAnalyticsService().fleet_report(report_date=metadata.report_date or metadata.as_of_date or date.today(),device_names=metadata.device_names))
        except Exception as exc:return self.result(False,ToolStatus.FAILED,"Selected-device intelligence report failed.",error=f"{type(exc).__name__}: {exc}")

class PatchTicketTool(_Base):
    name=ToolName.PATCH_TICKET
    def execute(self,request:ToolRequest)->ToolResult:
        metadata=request.metadata
        if not isinstance(metadata,PatchMetadata):return self.result(False,ToolStatus.REJECTED,"Patch metadata is required.",error="Invalid metadata")
        names=metadata.device_names or ([metadata.device_name] if metadata.device_name else [])
        if not names:return self.result(False,ToolStatus.REJECTED,"Select at least one device.",error="Missing devices")
        if not metadata.approval_granted:return self.result(False,ToolStatus.REJECTED,"Approval is required before creating tickets.",error="Approval required")
        results=[]
        for name in names:
            try:results.append(PatchTicketService().raise_for_device(name,reason=metadata.reason or metadata.ticket_reason,mode="USER",requested_by=request.requested_by))
            except Exception as exc:results.append({"success":False,"status":"FAILED","ticket_id":None,"device_name":name,"dry_run":False,"sent":False,"message":f"{type(exc).__name__}: {exc}"})
        succeeded=sum(bool(x.get("success")) for x in results)
        return self.result(succeeded==len(results),ToolStatus.COMPLETED if succeeded==len(results) else ToolStatus.FAILED,f"Ticket processing completed: {succeeded} succeeded, {len(results)-succeeded} failed.",result={"tickets":results,"succeeded":succeeded,"failed":len(results)-succeeded})
