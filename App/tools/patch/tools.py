from App.agents.patch_agent import PatchAgent
from App.workflow.state import IntentType,PatchMetadata
def get_patch_report(as_of_date=None,device_name=None,minimum_days=1):return PatchAgent().execute(IntentType.PATCH_REPORT,PatchMetadata(as_of_date=as_of_date,device_name=device_name,minimum_days=minimum_days),"tool","tool").model_dump(mode="json")
def run_patch_scan():return PatchAgent().execute(IntentType.PATCH_SCAN,PatchMetadata(),"tool","tool").model_dump(mode="json")
def raise_patch_ticket(device_name,reason=None,confirmed=False):return PatchAgent().execute(IntentType.PATCH_TICKET,PatchMetadata(device_name=device_name,ticket_reason=reason,approval_granted=confirmed),"tool","tool").model_dump(mode="json")
