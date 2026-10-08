from sqlalchemy import inspect
from App.db.connection import DB_SCHEMA,engine
from App.db.models.patch_compliance import PatchScanRun,PatchDeviceState,PatchDeviceObservation,PatchFinding,PatchTicket
MODELS=(PatchScanRun,PatchDeviceState,PatchDeviceObservation,PatchFinding,PatchTicket)
def setup():
 with engine.begin() as c:
  for m in MODELS:m.__table__.create(bind=c,checkfirst=True)
 for m in MODELS:
  if not inspect(engine).has_table(m.__tablename__,schema=DB_SCHEMA):raise RuntimeError(f"Missing {DB_SCHEMA}.{m.__tablename__}")
  print(f"Available: {DB_SCHEMA}.{m.__tablename__}")
if __name__=="__main__":setup()
