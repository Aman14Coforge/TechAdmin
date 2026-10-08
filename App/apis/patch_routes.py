from datetime import date
from fastapi import APIRouter,HTTPException,Query
from pydantic import BaseModel
from App.services.patch.service import PatchService
router=APIRouter(prefix="/api/v1/patch",tags=["patch-agent"])
class TicketRequest(BaseModel):device_name:str;reason:str|None=None;confirmed:bool=False
@router.post("/scan")
def scan():return {"success":True,"result":PatchService().scan()}
@router.get("/report")
def report(as_of:date|None=None,device_name:str|None=None,minimum_days:int=Query(1,ge=1,le=365)):return {"success":True,"result":PatchService().report(as_of,device_name,minimum_days)}
@router.post("/ticket")
def ticket(r:TicketRequest):
 if not r.confirmed:raise HTTPException(409,"Confirmation is required")
 try:return {"success":True,"result":PatchService().raise_ticket(r.device_name,r.reason)}
 except ValueError as e:raise HTTPException(404,str(e)) from e
