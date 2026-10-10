"""Device, multi-device and fleet patch analytics from persisted evidence."""
from __future__ import annotations
from collections import Counter,defaultdict
from datetime import date
from typing import Any
from App.services.patch.security_query_service import SecurityPatchQueryService
from App.services.patch.ollama_analyzer import OllamaSecurityAnalyzer

class PatchAnalyticsService:
    def __init__(self): self.query=SecurityPatchQueryService();self.ai=OllamaSecurityAnalyzer()
    @staticmethod
    def _patch_id(p):return str(p.get("KB number") or p.get("Patch name") or p.get("kb_number") or p.get("patch_name") or "Unknown")
    def device_report(self,device_name:str,*,report_date:date|None=None)->dict[str,Any]:
        d=self.query.device_details(device_name);history=sorted([x for x in d.get("history") or [] if not report_date or x["scan_date"]<=report_date.isoformat()],key=lambda x:x["scan_date"]);patches=Counter();severity=Counter();release=Counter();trend=[]
        for snap in history:
            trend.append({"Date":snap["scan_date"],"Missing patches":int(snap.get("missing_patch_count") or 0),"Risk score":float(snap.get("risk_score") or 0)})
            for p in snap.get("patches") or []:
                patches[self._patch_id(p)]+=1;severity[str(p.get("Severity") if p.get("Severity") is not None else "Unknown")]+=1
                released=p.get("Released");age=None
                try:age=((report_date or date.today())-date.fromisoformat(str(released)[:10])).days if released else None
                except ValueError:pass
                release["Unknown" if age is None else "0-30 days" if age<=30 else "31-90 days" if age<=90 else ">90 days"]+=1
        first=trend[0]["Missing patches"] if trend else 0;current=trend[-1]["Missing patches"] if trend else 0
        direction="insufficient_data" if len(trend)<2 else "improving" if current<first else "worsening" if current>first else "unchanged"
        evidence={"device":{k:d.get(k) for k in ("device_name","discovery_id","active","first_seen_date","last_seen_date","days_open","ticket_status","ticket_reference")},"summary":{"snapshots":len(history),"current_missing":current,"unique_patches":len(patches),"change":current-first,"direction":direction},"trend":trend,"severity":dict(severity),"release_age":dict(release),"persistent_patches":patches.most_common(30),"history":history}
        prompt_evidence={**evidence,"history":[{k:v for k,v in snap.items() if k!="patches"} for snap in history],"latest_patch_sample":(history[-1].get("patches") or [])[:30] if history else [],"data_limitations":["AI receives up to 30 latest patch details; complete evidence remains in the report."]}
        return {"report_type":"device","evidence":evidence,"ai":self.ai.analyze(prompt_evidence,report_type="device")}
    def fleet_report(self,*,report_date:date,device_names:list[str]|None=None)->dict[str,Any]:
        if not device_names:
            evidence=self.query.fleet_report_evidence(report_date)
            prompt_evidence={key:value for key,value in evidence.items() if key!="priority_devices"}
            prompt_evidence["priority_devices"]=evidence["priority_devices"]
            ai=self.ai.analyze(prompt_evidence,report_type="fleet")
            return {"report_type":"fleet","evidence":evidence,"ai":ai}

        # Resolve only selected devices instead of scanning every device in the fleet.
        all_rows=[];preloaded={};errors=[]
        for name in dict.fromkeys(str(value).strip() for value in device_names if str(value).strip()):
            try:
                details=self.query.device_details(name)
                preloaded[details["device_name"].upper()]=details
                snapshots=[item for item in details.get("history") or [] if item["scan_date"]<=report_date.isoformat()]
                latest=max(snapshots,key=lambda item:item["scan_date"]) if snapshots else None
                if latest:
                    all_rows.append({
                        "device_name":details["device_name"],"discovery_id":details["discovery_id"],
                        "ip_address":latest.get("ip_address"),"os_name":latest.get("os_name"),
                        "missing_patch_count":latest.get("missing_patch_count"),"risk_score":latest.get("risk_score"),
                        "consecutive_days":details.get("days_open"),"ticket_status":details.get("ticket_status"),
                        "ticket_reference":details.get("ticket_reference"),
                    })
            except Exception as exc:
                errors.append({"device_name":name,"error":f"{type(exc).__name__}: {exc}"})

        patch_devices=defaultdict(set);severity=Counter();device_reports=[]
        for row in all_rows:
            try:details=preloaded[row["device_name"].upper()]
            except Exception as exc:
                errors.append({"device_name":row["device_name"],"error":f"{type(exc).__name__}: {exc}"});continue
            snapshots=[x for x in details.get("history") or [] if x["scan_date"]<=report_date.isoformat()]
            latest=max(snapshots,key=lambda x:x["scan_date"]) if snapshots else None
            if latest:
                for p in latest.get("patches") or []:
                    patch_devices[self._patch_id(p)].add(row["device_name"]);severity[str(p.get("Severity") if p.get("Severity") is not None else "Unknown")]+=1
            device_reports.append({**row,"latest_patches":latest.get("patches",[]) if latest else []})
        priority=sorted(device_reports,key=lambda r:(float(r.get("risk_score") or 0),int(r.get("missing_patch_count") or 0),int(r.get("consecutive_days") or 0)),reverse=True)
        evidence={"scope":"selected_devices","snapshot":report_date.isoformat(),"summary":{"devices":len(device_reports),"total_missing_instances":sum(int(x.get("missing_patch_count") or 0) for x in device_reports),"ticket_eligible":sum(bool(x.get("ticket_eligible")) for x in device_reports)},"top_missing_patches":[{"patch":p,"affected_devices":len(ds)} for p,ds in sorted(patch_devices.items(),key=lambda x:len(x[1]),reverse=True)[:30]],"priority_devices":[{k:r.get(k) for k in ("device_name","missing_patch_count","risk_score","consecutive_days","ticket_status")} for r in priority[:30]],"severity":dict(severity),"devices":device_reports}
        evidence["data_errors"]=errors
        if device_names:
            found={str(x["device_name"]).upper() for x in device_reports}
            evidence["unavailable_devices"]=[x for x in device_names if x.upper() not in found]
        prompt_evidence={k:v for k,v in evidence.items() if k!="devices"}
        prompt_evidence["data_limitations"]=["Priority list contains up to 30 devices; aggregate counts cover the complete selected scope."]
        return {"report_type":"multi_device" if device_names else "fleet","evidence":evidence,"ai":self.ai.analyze(prompt_evidence,report_type="multi_device" if device_names else "fleet")}
