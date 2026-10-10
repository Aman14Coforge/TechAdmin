"""Robust iEngage HTTP-200 response normalization."""
from __future__ import annotations
import json,re
from typing import Any
TICKET_KEYS=("ticket_id","ticketId","ticketID","request_id","requestId","incident_id","incidentId","case_id","caseId","id","number","ticketNumber","requestNumber")
SUCCESS_KEYS=("success","isSuccess","succeeded","status","result","message")

def _walk(value:Any):
    yield value
    if isinstance(value,dict):
        for v in value.values():yield from _walk(v)
    elif isinstance(value,list):
        for v in value:yield from _walk(v)

def normalize_iengage_response(*,http_status:int,body:Any,device_name:str,dry_run:bool)->dict[str,Any]:
    parsed=body
    if isinstance(body,(bytes,bytearray)):body=body.decode("utf-8","replace")
    if isinstance(body,str):
        try:parsed=json.loads(body)
        except json.JSONDecodeError:parsed={"raw":body}
    ticket_id=None
    for node in _walk(parsed):
        if isinstance(node,dict):
            for key in TICKET_KEYS:
                value=node.get(key)
                if value not in (None,"",0) and str(value).upper() not in {"TRUE","FALSE","SUCCESS","OK"}:
                    ticket_id=str(value);break
        if ticket_id:break
    raw_text=json.dumps(parsed,default=str) if not isinstance(body,str) else body
    if not ticket_id:
        m=re.search(r"(?i)(?:ticket|request|incident|case)(?:\s*(?:id|number|no))?\s*[:=#-]?\s*([A-Z0-9][A-Z0-9_-]{3,})",raw_text)
        if m:ticket_id=m.group(1)
    success_marker=False
    for node in _walk(parsed):
        if isinstance(node,dict):
            for key in SUCCESS_KEYS:
                value=node.get(key)
                if value is True or str(value).strip().casefold() in {"true","success","successful","created","completed","ok"}:success_marker=True
    success=http_status in range(200,300) and bool(ticket_id or success_marker)
    return {"success":success,"status":"CREATED" if success and ticket_id else "ACCEPTED" if success else "FAILED","ticket_id":ticket_id,"device_name":device_name,"dry_run":dry_run,"message":f"Ticket {ticket_id} was created successfully." if ticket_id else "iEngage accepted the request." if success else f"iEngage returned HTTP {http_status}, but no recognized ticket identifier or success marker was found.","http_status":http_status,"raw_response":parsed}
