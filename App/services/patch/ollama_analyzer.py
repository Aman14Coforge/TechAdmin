"""Strict, observable Ollama analysis. Never silently pretends AI succeeded."""
from __future__ import annotations
import json
from typing import Any
from loguru import logger
from langchain_ollama import ChatOllama
from App.services.patch.config import settings

SYSTEM_PROMPT = """You are TechAdmin's senior Ivanti endpoint-security analyst.
Use ONLY supplied evidence. Separate confirmed facts from hypotheses. Never invent
CVEs, causes, logons, deployment attempts, return codes, reboot state, disk state,
policies, or ticket outcomes. Make the report useful without requiring the operator
to inspect raw rows. Return one JSON object exactly matching the requested schema.
"""

DEVICE_SCHEMA = {
 "executive_summary":"string",
 "compliance":{"direction":"improving|worsening|unchanged|insufficient_data","confidence":"high|medium|limited","explanation":"string"},
 "risk":{"level":"critical|high|medium|low|unknown","explanation":"string"},
 "key_findings":["string"],
 "persistent_exposure":["string"],
 "release_age_insights":["string"],
 "operator_checks":[{"priority":1,"check":"string","why":"string","evidence_needed":["string"]}],
 "hypotheses":[{"hypothesis":"string","status":"requires_verification","supporting_evidence":["string"],"evidence_needed":["string"]}],
 "recommended_actions":[{"priority":1,"action":"string","reason":"string"}],
 "ticket_recommendation":{"recommended":False,"reason":"string"},
 "data_limitations":["string"]
}

FLEET_SCHEMA = {
 "executive_summary":"string",
 "fleet_risk":{"level":"critical|high|medium|low|unknown","explanation":"string"},
 "priority_devices":[{"device_name":"string","reason":"string","priority":1}],
 "top_patch_exposures":[{"patch":"string","affected_devices":1,"reason":"string"}],
 "cross_fleet_patterns":["string"],
 "operator_checks":["string"],
 "recommended_actions":[{"priority":1,"action":"string","reason":"string"}],
 "data_limitations":["string"]
}

class OllamaAnalysisError(RuntimeError): pass

class OllamaSecurityAnalyzer:
    def __init__(self) -> None:
        self.model = settings.ai_model
        self.host = settings.ollama_host

    def analyze(self, evidence: dict[str,Any], *, report_type:str) -> dict[str,Any]:
        schema = FLEET_SCHEMA if report_type in {"fleet","multi_device"} else DEVICE_SCHEMA
        prompt = SYSTEM_PROMPT + "\nRequired schema:\n" + json.dumps(schema) + "\nEvidence:\n" + json.dumps(evidence,default=str,ensure_ascii=False)
        logger.info("SECURITY_OLLAMA_START | model={} | host={} | type={}", self.model,self.host,report_type)
        try:
            response=ChatOllama(model=self.model,base_url=self.host,temperature=0,format="json",timeout=180).invoke(prompt)
            raw=response.content if isinstance(response.content,str) else json.dumps(response.content)
            parsed=json.loads(raw)
            if not isinstance(parsed,dict) or not parsed.get("executive_summary"):
                raise OllamaAnalysisError("Ollama returned JSON without executive_summary")
            logger.info("SECURITY_OLLAMA_SUCCESS | model={} | type={}",self.model,report_type)
            return {"available":True,"model":self.model,"host":self.host,"analysis":parsed,"error":None}
        except Exception as exc:
            logger.exception("SECURITY_OLLAMA_FAILED | model={} | host={} | type={} | error={}",self.model,self.host,report_type,type(exc).__name__)
            return {"available":False,"model":self.model,"host":self.host,"analysis":None,"error":f"{type(exc).__name__}: {exc}"}
