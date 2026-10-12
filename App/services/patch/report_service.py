from __future__ import annotations
import json
from collections import Counter
from datetime import date
from html import escape
from typing import Any
from sqlalchemy import and_, select
from App.db.connection import SessionLocal
from App.db.models.patch_compliance import PatchDeviceObservation, PatchDeviceState, PatchFinding

class PatchReportService:
    def build(self, *, start_date: date, end_date: date, device_name: str|None=None, patch_query: str|None=None, include_resolved: bool=True) -> dict[str,Any]:
        with SessionLocal() as db:
            q=select(PatchDeviceObservation,PatchDeviceState).join(PatchDeviceState,PatchDeviceState.discovery_id==PatchDeviceObservation.discovery_id).where(PatchDeviceObservation.scan_date.between(start_date,end_date))
            if device_name: q=q.where(PatchDeviceObservation.device_name.ilike(f"%{device_name}%"))
            if not include_resolved: q=q.where(PatchDeviceState.is_active.is_(True))
            pairs=db.execute(q.order_by(PatchDeviceObservation.scan_date.desc(),PatchDeviceObservation.missing_patch_count.desc())).all()
            ids={(o.scan_date,o.discovery_id) for o,_ in pairs}
            fq=select(PatchFinding).where(PatchFinding.scan_date.between(start_date,end_date),PatchFinding.evidence_type=="CONFIRMED_MISSING")
            if patch_query: fq=fq.where(PatchFinding.patch_name.ilike(f"%{patch_query}%"))
            findings=list(db.scalars(fq).all())
        allowed={(d,i) for d,i in ids}; findings=[f for f in findings if (f.scan_date,f.discovery_id) in allowed]
        patch_counts=Counter((f.patch_name or f.kb_number or "Unknown patch") for f in findings)
        devices=[]
        for o,s in pairs:
            dev_find=[f for f in findings if f.scan_date==o.scan_date and f.discovery_id==o.discovery_id]
            if patch_query and not dev_find: continue
            devices.append({"scan_date":o.scan_date.isoformat(),"device_name":o.device_name,"discovery_id":o.discovery_id,"ip_address":o.ip_address,"os_name":o.os_name,"missing_patch_count":o.missing_patch_count,"risk_score":o.risk_score,"first_seen_date":s.first_seen_date.isoformat(),"last_seen_date":s.last_seen_date.isoformat(),"days_open":s.consecutive_days,"active":s.is_active,"resolved_at":s.resolved_at.isoformat() if s.resolved_at else None,"ticket_status":s.ticket_status,"ticket_reference":s.ticket_reference,"patches":[{"name":f.patch_name,"kb":f.kb_number,"severity":f.severity,"released_at":f.released_at.isoformat() if f.released_at else None} for f in dev_find]})
        return {"period":{"start":start_date.isoformat(),"end":end_date.isoformat()},"summary":{"observations":len(devices),"unique_devices":len({d['discovery_id'] for d in devices}),"missing_patch_instances":sum(d['missing_patch_count'] for d in devices),"active_devices":len({d['discovery_id'] for d in devices if d['active']}),"resolved_devices":len({d['discovery_id'] for d in devices if not d['active']})},"top_missing_patches":[{"patch":p,"occurrences":c} for p,c in patch_counts.most_common(20)],"devices":devices}
    @staticmethod
    def to_json(report:dict[str,Any])->bytes: return json.dumps(report,indent=2,ensure_ascii=False).encode()
    @staticmethod
    def to_html(report:dict[str,Any])->bytes:
        s=report['summary']; rows=''.join(f"<tr><td>{escape(d['scan_date'])}</td><td>{escape(d['device_name'])}</td><td>{d['missing_patch_count']}</td><td>{d['days_open']}</td><td>{escape(d['ticket_reference'] or '')}</td></tr>" for d in report['devices'])
        return f"<!doctype html><html><head><meta charset='utf-8'><style>body{{font-family:Segoe UI;color:#1B2433;margin:36px}}.cards{{display:flex;gap:12px}}.card{{border:1px solid #e6e9ef;border-radius:12px;padding:14px 18px}}table{{border-collapse:collapse;width:100%;margin-top:20px}}th,td{{border-bottom:1px solid #eee;padding:9px;text-align:left}}</style></head><body><h1>Ivanti Patch Compliance Report</h1><p>{report['period']['start']} to {report['period']['end']}</p><div class='cards'><div class='card'>Unique devices<br><b>{s['unique_devices']}</b></div><div class='card'>Missing instances<br><b>{s['missing_patch_instances']}</b></div><div class='card'>Resolved devices<br><b>{s['resolved_devices']}</b></div></div><h2>Device observations</h2><table><tr><th>Date</th><th>Device</th><th>Missing</th><th>Days open</th><th>Ticket</th></tr>{rows}</table></body></html>".encode()
