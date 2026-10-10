from sqlalchemy import text
from App.db.connection import DB_SCHEMA, engine
from App.db.models.patch_compliance import PatchTicketBatch, PatchTicketBatchItem
ALTERS=[
"ALTER TABLE {s}.patch_scan_runs ADD COLUMN IF NOT EXISTS source VARCHAR(40) DEFAULT 'MANUAL'",
"ALTER TABLE {s}.patch_scan_runs ADD COLUMN IF NOT EXISTS resolved_devices INTEGER DEFAULT 0",
"ALTER TABLE {s}.patch_scan_runs ADD COLUMN IF NOT EXISTS tickets_created INTEGER DEFAULT 0",
"ALTER TABLE {s}.patch_device_states ADD COLUMN IF NOT EXISTS ticket_created_at TIMESTAMPTZ",
"ALTER TABLE {s}.patch_tickets ADD COLUMN IF NOT EXISTS requested_by VARCHAR(255)",
"ALTER TABLE {s}.patch_tickets ADD COLUMN IF NOT EXISTS error_message TEXT",
"ALTER TABLE {s}.patch_tickets ADD COLUMN IF NOT EXISTS attempt_count INTEGER DEFAULT 0",
"ALTER TABLE {s}.patch_tickets ADD COLUMN IF NOT EXISTS completed_at TIMESTAMPTZ",
]
def main():
    with engine.begin() as c:
        for statement in ALTERS:c.execute(text(statement.format(s=DB_SCHEMA)))
        PatchTicketBatch.__table__.create(bind=c,checkfirst=True);PatchTicketBatchItem.__table__.create(bind=c,checkfirst=True)
    print('Patch compliance migration completed.')
if __name__=='__main__':main()
