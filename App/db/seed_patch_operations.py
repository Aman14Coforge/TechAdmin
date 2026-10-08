from sqlalchemy import select
from App.db.connection import SessionLocal
from App.db.models.operations import Operation
PATCH_OPERATIONS=[
 {"operation_code":"PATCH_REPORT","operation_name":"Get Patch Compliance Report","execution_type":"API","tool_name":"get_patch_report","script_name":None,"risk_level":"LOW","requires_approval":False,"is_active":True},
 {"operation_code":"PATCH_TICKET","operation_name":"Raise Patch Compliance Ticket","execution_type":"API","tool_name":"raise_patch_ticket","script_name":None,"risk_level":"HIGH","requires_approval":True,"is_active":True},
 {"operation_code":"PATCH_SCAN","operation_name":"Run Ivanti Patch Scan","execution_type":"JOB","tool_name":"run_patch_scan","script_name":None,"risk_level":"MEDIUM","requires_approval":False,"is_active":True},
]
def seed():
 with SessionLocal() as db:
  for item in PATCH_OPERATIONS:
   row=db.scalar(select(Operation).where(Operation.operation_code==item["operation_code"]))
   if row is None:db.add(Operation(**item))
   else:
    for key,value in item.items():
     if key not in {"operation_code"}:setattr(row,key,value)
  db.commit()
 print("Patch operations seeded successfully")
if __name__=="__main__":seed()
