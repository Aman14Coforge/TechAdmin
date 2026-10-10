"""Functions exposed by the TechAdmin patch MCP server."""
from __future__ import annotations
from datetime import date
from uuid import uuid4
from App.agents.patch_agent import PatchAgent
from App.tools.patch.security_tools import PatchDeviceReportTool,PatchFleetReportTool,PatchSelectedReportTool,PatchTicketTool
from App.workflow.state import IntentType,PatchMetadata,ToolRequest

def _request(intent:IntentType,metadata:PatchMetadata,requested_by:str|None=None)->ToolRequest:
    return ToolRequest(request_id=f"req_{uuid4().hex}",correlation_id=f"corr_{uuid4().hex}",intent=intent,metadata=metadata,requested_by=requested_by)

def get_patch_report(as_of_date=None,device_name=None,minimum_days=1):
    return PatchAgent().execute(IntentType.PATCH_REPORT,PatchMetadata(as_of_date=as_of_date,device_name=device_name,minimum_days=minimum_days),"tool","tool").model_dump(mode="json")
def run_patch_scan():return PatchAgent().execute(IntentType.PATCH_SCAN,PatchMetadata(),"tool","tool").model_dump(mode="json")
def generate_patch_device_report(device_name:str,report_date:date|None=None):return PatchDeviceReportTool().execute(_request(IntentType.PATCH_DEVICE_REPORT,PatchMetadata(device_name=device_name,report_date=report_date))).model_dump(mode="json")
def generate_patch_fleet_report(report_date:date|None=None):return PatchFleetReportTool().execute(_request(IntentType.PATCH_FLEET_REPORT,PatchMetadata(report_date=report_date))).model_dump(mode="json")
def generate_selected_devices_report(device_names:list[str],report_date:date|None=None):return PatchSelectedReportTool().execute(_request(IntentType.PATCH_SELECTED_REPORT,PatchMetadata(device_names=device_names,report_date=report_date))).model_dump(mode="json")
def raise_patch_ticket(device_name:str|None=None,device_names:list[str]|None=None,reason:str|None=None,confirmed:bool=False,requested_by:str|None=None):
    metadata=PatchMetadata(device_name=device_name,device_names=device_names or [],ticket_reason=reason,reason=reason,approval_granted=confirmed)
    return PatchTicketTool().execute(_request(IntentType.PATCH_TICKET,metadata,requested_by)).model_dump(mode="json")
