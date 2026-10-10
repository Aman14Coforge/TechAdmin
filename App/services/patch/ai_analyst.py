from __future__ import annotations
import json
import requests
from typing import Any
from App.services.patch.config import settings
class PatchAIAnalyst:
    def analyze(self, report:dict[str,Any])->dict[str,Any]:
        s=report['summary']; top=report.get('top_missing_patches',[])[:5]
        fallback={"executive_summary":f"The selected period contains {s['unique_devices']} unique non-compliant devices and {s['missing_patch_instances']} missing patch instances. {s['resolved_devices']} devices are present as resolved historical records.","priority_actions":["Prioritize active devices with the highest risk score and longest open duration.","Review devices at or beyond the automatic ticket threshold.","Validate recurring top patches for deployment or reboot failures."],"top_patch_observation":top,"analysis_source":"Deterministic database evidence"}
        if not settings.ai_enabled:return fallback
        payload={"summary":s,"top_missing_patches":top,"highest_risk":sorted(report.get('devices',[]),key=lambda x:(x.get('risk_score') or 0,x.get('days_open') or 0),reverse=True)[:15]}
        prompt="Analyze only this verified patch-compliance JSON. Do not invent facts, devices, counts, dates, patches or tickets. Return JSON with executive_summary, priority_actions (array), risks (array), limitations.\n"+json.dumps(payload,default=str)
        try:
            r=requests.post(f"{settings.ollama_host}/api/generate",json={"model":settings.ai_model,"prompt":prompt,"stream":False,"format":"json"},timeout=120); r.raise_for_status(); out=json.loads(r.json()['response']); out['analysis_source']=f"Ollama evidence analysis ({settings.ai_model})"; return out
        except Exception:return fallback
