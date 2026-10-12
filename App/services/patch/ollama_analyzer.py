"""Strict, observable Ollama analysis. Never silently pretends AI succeeded."""
from __future__ import annotations
import json
from typing import Any
from loguru import logger
from langchain_ollama import ChatOllama
from App.services.patch.config import settings

SYSTEM_PROMPT = """You are TechAdmin's senior Ivanti endpoint-security analyst.
Use ONLY supplied evidence. Calculate the actual observed trend before describing
improvement or deterioration. A high point-in-time risk score is not by itself a
trend. Severity values are vendor numeric codes; do not relabel them critical/high
unless the evidence supplies that mapping. Separate counts and facts from
hypotheses. Never invent CVEs, causes, logons, deployment attempts, return codes,
reboot state, disk state, policies, or ticket outcomes. Prioritize actionable
insights: concentration, persistence, change between snapshots, old exposure,
and the highest-risk named endpoints. Mention evidence limits. Return one JSON
object exactly matching the requested schema.
"""

DEVICE_SCHEMA = {
 "executive_summary":"string",
 "compliance":{"direction":"improving|worsening|unchanged|insufficient_data","confidence":"high|medium|limited","explanation":"string"},
 "risk":{"level":"critical|high|medium|low|unknown","explanation":"string"},
 "key_findings":["string"],
 "persistent_exposure":["string"],
 "change_since_previous_snapshot":{"new_missing_patches":["string"],"cleared_patches":["string"],"explanation":"string"},
 "release_age_insights":["string"],
 "operator_checks":[{"priority":1,"check":"string","why":"string","evidence_needed":["string"]}],
 "hypotheses":[{"hypothesis":"string","status":"requires_verification","supporting_evidence":["string"],"evidence_needed":["string"]}],
 "recommended_actions":[{"priority":1,"action":"string","reason":"string"}],
 "ticket_recommendation":{"recommended":False,"reason":"string"},
 "data_limitations":["string"]
}

FLEET_SCHEMA = {
 "executive_summary":"string",
 "resolved_devices":{"count":1,"trend":"string"},
 "fleet_risk":{"level":"critical|high|medium|low|unknown","explanation":"string"},
 "priority_devices":[{"device_name":"string","reason":"string","priority":1}],
 "top_patch_exposures":[{"patch":"string","affected_devices":1,"reason":"string"}],
 "cross_fleet_patterns":["string"],
 "trend_insights":["string"],
 "risk_concentration":{"high_risk_devices":1,"persistent_14_day_devices":1,"explanation":"string"},
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
            response=ChatOllama(model=self.model,base_url=self.host,temperature=0,format="json",timeout=75,num_predict=640).invoke(prompt)
            raw=response.content if isinstance(response.content,str) else json.dumps(response.content)
            parsed=self._parse_json(raw)
            parsed=self._normalize_analysis(parsed,evidence,report_type)
            if not parsed.get("executive_summary"):
                raise OllamaAnalysisError("Ollama returned JSON without a usable summary")
            evidence_only=parsed.pop("_evidence_only_fallback",False)
            logger.info("SECURITY_OLLAMA_SUCCESS | model={} | type={}",self.model,report_type)
            return {"available":not evidence_only,"model":self.model,"host":self.host,"analysis":parsed,
                    "error":"Ollama returned incomplete analysis; showing evidence-based analysis instead." if evidence_only else None,
                    "fallback":"evidence_based" if evidence_only else None}
        except Exception as exc:
            logger.exception("SECURITY_OLLAMA_FAILED | model={} | host={} | type={} | error={}",self.model,self.host,report_type,type(exc).__name__)
            fallback=self._evidence_analysis(evidence,report_type)
            return {"available":False,"model":self.model,"host":self.host,"analysis":fallback,"error":f"{type(exc).__name__}: {exc}","fallback":"evidence_based"}

    @staticmethod
    def _parse_json(raw:str)->dict[str,Any]:
        text=str(raw or "").strip()
        if text.startswith("```"):
            text=text.strip("`")
            if text[:4].casefold()=="json":text=text[4:].strip()
        try:value=json.loads(text)
        except json.JSONDecodeError:
            start=text.find("{");end=text.rfind("}")
            if start<0 or end<=start:raise
            value=json.loads(text[start:end+1])
        if not isinstance(value,dict):raise OllamaAnalysisError("Ollama returned a non-object JSON response")
        nested=value.get("analysis")
        if isinstance(nested,dict) and not any(key in value for key in ("executive_summary","executiveSummary","summary")):
            value=nested
        return value

    @staticmethod
    def _normalize_analysis(parsed:dict[str,Any],evidence:dict[str,Any],report_type:str)->dict[str,Any]:
        normalized={str(key).strip().casefold().replace(" ","_"):value for key,value in parsed.items()}
        summary=(normalized.get("executive_summary") or normalized.get("executivesummary")
             or normalized.get("summary") or normalized.get("overview") or normalized.get("response"))
        if isinstance(summary,dict):summary=summary.get("text") or summary.get("summary") or json.dumps(summary,ensure_ascii=False)
        if isinstance(summary,list):summary=" ".join(str(value) for value in summary)
        if not summary:
            findings=normalized.get("key_findings") or normalized.get("findings") or []
            if isinstance(findings,list) and findings:summary=" ".join(map(str,findings[:3]))
        evidence_only=False
        if not summary:
            summary=OllamaSecurityAnalyzer._evidence_analysis(evidence,report_type)["executive_summary"]
            evidence_only=True
        normalized["executive_summary"]=str(summary)
        if evidence_only:normalized["_evidence_only_fallback"]=True
        aliases={"risk_assessment":"risk","fleet_risk_assessment":"fleet_risk","actions":"recommended_actions","findings":"key_findings"}
        for source,target in aliases.items():
            if target not in normalized and source in normalized:normalized[target]=normalized[source]
        return normalized

    @staticmethod
    def _evidence_analysis(evidence:dict[str,Any],report_type:str)->dict[str,Any]:
        summary=evidence.get("summary") or {};scope=evidence.get("device") or {}
        if report_type in {"fleet","multi_device"}:
            count=int(summary.get("devices") or 0);missing=int(summary.get("total_missing_instances") or 0)
            high=int(summary.get("high_risk_devices") or 0);persistent=int(summary.get("persistent_14_day_devices",summary.get("ticket_eligible")) or 0)
            resolved=int(summary.get("resolved_devices") or 0)
            ranked=evidence.get("priority_devices") or []
            names=[str(row.get("device_name")) for row in ranked[:5] if row.get("device_name")]
            patches=evidence.get("top_missing_patches") or []
            common=[str(row.get("patch")) for row in patches[:3] if row.get("patch")]
            text=f"The {evidence.get('scope','endpoint')} snapshot for {evidence.get('snapshot','the selected date')} contains {count:,} non-compliant devices and {missing:,} missing patch instances."
            if high:text+=f" {high:,} devices have risk scores of 80 or higher."
            if persistent:text+=f" {persistent:,} devices have remained non-compliant for at least 14 days."
            if resolved:text+=f" {resolved:,} archived devices are recorded as resolved by this date."
            if names:text+=f" Highest-priority devices include {', '.join(names)}."
            if common:text+=f" Most widespread missing patches include {', '.join(common)}."
            return {"executive_summary":text,"resolved_devices":{"count":resolved,"trend":"Resolved endpoints are counted from archived device states through the selected date."},"fleet_risk":{"level":"high" if high else "medium" if count else "low","explanation":f"Observed {count:,} affected devices, {missing:,} missing-patch instances and {high:,} high-risk devices."},"priority_devices":[{"device_name":row.get("device_name"),"reason":f"{row.get('missing_patch_count',0)} missing; risk {row.get('risk_score','unknown')}; {row.get('consecutive_days',0)} days open","priority":index+1} for index,row in enumerate(ranked[:10])],"top_patch_exposures":[{"patch":row.get("patch"),"affected_devices":row.get("affected_devices"),"reason":"Most frequently observed across the fleet."} for row in patches[:10]],"cross_fleet_patterns":[f"{count:,} devices have confirmed non-compliance in this snapshot.",f"{missing:,} missing patch instances are recorded."],"trend_insights":[f"{row.get('date')}: {row.get('devices')} devices, {row.get('missing_instances')} missing instances." for row in (evidence.get("trend") or [])[-5:]],"risk_concentration":{"high_risk_devices":high,"persistent_14_day_devices":persistent,"explanation":"Calculated from stored Ivanti risk scores and consecutive non-compliance duration."},"operator_checks":["Review high-risk endpoints and confirm maintenance windows before remediation."],"recommended_actions":[{"priority":1,"action":"Review and remediate the highest-risk devices.","reason":"Prioritize endpoints with the largest risk scores and missing-patch counts."}],"data_limitations":evidence.get("data_limitations") or []}
        name=scope.get("device_name") or "the selected device";missing=int(summary.get("current_missing") or 0)
        direction=summary.get("direction","insufficient_data")
        return {"executive_summary":f"{name} has {missing} missing patches in the latest available snapshot. The observed trend is {direction}; {summary.get('persistent_across_all_snapshots',0)} patches persisted across every stored snapshot.","compliance":{"direction":direction,"confidence":"high" if summary.get("snapshots",0)>1 else "limited","explanation":f"Compared {summary.get('snapshots',0)} stored snapshots; missing-patch count changed by {summary.get('missing_change_since_first_snapshot',0)}."},"risk":{"level":"high" if float((evidence.get('trend') or [{}])[-1].get('risk_score') or 0)>=80 else "medium" if missing else "low","explanation":"Based on the stored Ivanti risk score and missing-patch count."},"key_findings":[f"{missing} missing patches in the latest snapshot.",f"{summary.get('new_since_previous_snapshot',0)} newly missing and {summary.get('cleared_since_previous_snapshot',0)} cleared since the previous snapshot."],"persistent_exposure":[str(value) for value in evidence.get("persistent_patch_ids",[])[:10]],"change_since_previous_snapshot":{"new_missing_patches":evidence.get("new_patch_ids_since_previous",[])[:10],"cleared_patches":evidence.get("cleared_patch_ids_since_previous",[])[:10],"explanation":"Compared the last two stored Ivanti snapshots."},"release_age_insights":[f"{key}: {value} patch instances." for key,value in (evidence.get("latest_release_age_counts") or {}).items()],"operator_checks":[{"priority":1,"check":"Review missing patches and maintenance window.","why":"Confirm applicability before deployment.","evidence_needed":["Endpoint change window","Patch deployment status"]}],"hypotheses":[],"recommended_actions":[{"priority":1,"action":"Prioritize the oldest and highest-risk missing patches.","reason":"Reduce observed exposure while confirming applicability."}],"ticket_recommendation":{"recommended":bool(scope.get("active") and missing and int(scope.get("days_open") or 0)>=14),"reason":"Eligibility is based on active state, configured persistence threshold and missing patches."},"data_limitations":evidence.get("data_limitations") or []}
