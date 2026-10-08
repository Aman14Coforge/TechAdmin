from __future__ import annotations
from datetime import datetime,timezone
from typing import Any,Literal,TypedDict
from uuid import uuid4
from langgraph.graph import END,START,StateGraph
from loguru import logger
from App.agents.identity_agent import IdentityAgent
from App.agents.patch_agent import PatchAgent
from App.db.operation_audit import close_request,open_request
from App.guardrails import guardrail_engine
from App.intent.patch_extractor import DeterministicPatchExtractor
from App.intent.unified_extractor import UnifiedIntentMetadataExtractor
from App.services.password_vault import password_vault
from App.workflow.router import AgentRouter
from App.workflow.state import AgentExecutionResult,AgentType,ExecutionBackend,IntentType,PatchMetadata,RoutingResult,UnifiedExtractionResult
class TechAdminGraphState(TypedDict,total=False):
 user_input:str;request_id:str;correlation_id:str;confirmed:bool;requester_id:str|None;requester_role:str|None;extraction:UnifiedExtractionResult|None;routing:RoutingResult|None;agent_result:AgentExecutionResult|None;guardrail_decision:Any;response:dict[str,Any]|None;stage:str;error:str|None
class TechAdminWorkflow:
 MINIMUM_INTENT_CONFIDENCE=.70
 def __init__(self,extractor=None,router=None,identity_agent=None,patch_agent=None):self.extractor=extractor or UnifiedIntentMetadataExtractor();self.patch_extractor=DeterministicPatchExtractor();self.router=router or AgentRouter();self.identity_agent=identity_agent or IdentityAgent();self.patch_agent=patch_agent or PatchAgent();self.graph=self._build_graph()
 def _build_graph(self):
  b=StateGraph(TechAdminGraphState)
  for n,f in [("validate_input",self._validate),("input_guardrail",self._input_guardrail),("extract_request",self._extract),("confidence_gate",self._confidence),("request_guardrail",self._request_guardrail),("apply_trusted_approval",self._approval),("route_agent",self._route),("execute_identity_agent",self._identity),("execute_patch_agent",self._patch),("build_agent_response",self._build_response),("finalize_response",self._finalize)]:b.add_node(n,f)
  b.add_edge(START,"validate_input");
  b.add_conditional_edges("validate_input",self._stop,{"continue":"input_guardrail","finalize":"finalize_response"});
  b.add_conditional_edges("input_guardrail",self._stop,{"continue":"extract_request","finalize":"finalize_response"});
  b.add_conditional_edges("extract_request",self._stop,{"continue":"confidence_gate","finalize":"finalize_response"});
  b.add_conditional_edges("confidence_gate",self._stop,{"continue":"request_guardrail","finalize":"finalize_response"});
  b.add_conditional_edges("request_guardrail",self._stop,{"continue":"apply_trusted_approval","finalize":"finalize_response"});
  b.add_edge("apply_trusted_approval","route_agent");
  b.add_conditional_edges("route_agent",self._after_route,{"identity":"execute_identity_agent","patch":"execute_patch_agent","finalize":"finalize_response"});
  b.add_edge("execute_identity_agent","build_agent_response");
  b.add_edge("execute_patch_agent","build_agent_response");
  b.add_edge("build_agent_response","finalize_response");
  b.add_edge("finalize_response",END);
  return b.compile()
 @staticmethod
 def _stop(s):return "finalize" if isinstance(s.get("response"),dict) else "continue"
 @staticmethod
 def _after_route(s):
  if isinstance(s.get("response"),dict):return "finalize"
  r=s.get("routing");return "patch" if r and r.agent_type is AgentType.PATCH else "identity"
 def _validate(self,s):
  q=(s.get("user_input") or "").strip();u={"user_input":q,"request_id":s.get("request_id") or f"demo_{uuid4().hex[:12]}","correlation_id":s.get("correlation_id") or f"corr_{uuid4().hex}","stage":"validate_input"}
  if not q:u["response"]=self._failure(u["request_id"],u["correlation_id"],"User input cannot be empty.","Empty user input")
  return u
 def _input_guardrail(self,s):
  d=guardrail_engine.validate_input(s["user_input"],s["request_id"]);u={"guardrail_decision":d,"stage":"input_guardrail"}
  if d.blocked:u["response"]=self._guardrail_response(s["request_id"],s["correlation_id"],s["user_input"],d)
  return u
 def _extract(self,s):
  e=self.patch_extractor.extract(s["user_input"]) if self.patch_extractor.matches(s["user_input"]) else self.extractor.extract_all(s["user_input"]);u={"extraction":e,"stage":"extract_request"}
  if not e.success:u["response"]=self._base(s,e,e.explanation,e.error)
  return u
 def _confidence(self,s):
  e=s.get("extraction");u={"stage":"confidence_gate"}
  if not e or e.confidence<self.MINIMUM_INTENT_CONFIDENCE:u["response"]=self._base(s,e,"The intent confidence is too low to continue safely.","Low intent confidence") if e else self._failure(s["request_id"],s["correlation_id"],"Extraction unavailable","Extraction unavailable")
  return u
 def _request_guardrail(self,s):
  e=s["extraction"]
  d=guardrail_engine.validate_request(intent=e.intent.value,metadata=e.metadata.model_dump(mode="json"),request_id=s["request_id"],requester_id=s.get("requester_id"),requester_role=s.get("requester_role"),confirmed=bool(s.get("confirmed")));u={"guardrail_decision":d,"stage":"request_guardrail"}
  if d.blocked or d.needs_confirmation:u["response"]=self._guardrail_response(s["request_id"],s["correlation_id"],s["user_input"],d,e)
  return u
 def _approval(self,s):
  e=s["extraction"]
  if s.get("confirmed") and hasattr(e.metadata,"approval_granted"):e=e.model_copy(update={"metadata":e.metadata.model_copy(update={"approval_granted":True})})
  return {"extraction":e,"stage":"apply_trusted_approval"}
 def _route(self,s):
  try:return {"routing":self.router.route(s["extraction"].intent,s["extraction"].metadata.model_dump(mode="json")),"stage":"route_agent"}
  except ValueError as x:return {"stage":"route_agent","response":self._base(s,s["extraction"],str(x),type(x).__name__)}
 def _identity(self,s):
  e=s["extraction"]
  try:return {"agent_result":self.identity_agent.execute(operation=e.intent,metadata=e.metadata,request_id=s["request_id"],correlation_id=s["correlation_id"]),"stage":"execute_identity_agent"}
  except Exception as x:return {"response":self._base(s,e,"Identity Agent execution failed.",type(x).__name__),"stage":"execute_identity_agent"}
 def _patch(self,s):
  e=s["extraction"]
  try:return {"agent_result":self.patch_agent.execute(e.intent,e.metadata,s["request_id"],s["correlation_id"]),"stage":"execute_patch_agent"}
  except Exception as x:return {"response":self._base(s,e,"Patch Agent execution failed.",type(x).__name__),"stage":"execute_patch_agent"}
 def _build_response(self,s):
  if isinstance(s.get("response"),dict):return {"stage":"build_agent_response"}
  e=s["extraction"];a=s["agent_result"];tr=a.tool_result.model_dump(mode="json") if a.tool_result else None
  if e.intent is IntentType.PASSWORD_RESET:tr=self._rehome(tr)
  return {"stage":"build_agent_response","response":{"success":a.success,"request_id":s["request_id"],"correlation_id":s["correlation_id"],"user_input":s["user_input"],"intent":e.intent.value,"confidence":e.confidence,"explanation":e.explanation,"metadata":a.metadata.model_dump(mode="json"),"validation":a.validation.model_dump(mode="json"),"selected_agent":a.selected_agent,"selected_tool":a.selected_tool.value if a.selected_tool else None,"tool_result":tr,"clarification_required":a.clarification_required,"clarification_question":a.clarification_question,"message":a.message,"error":a.error}}
 def _finalize(self,s):
  r=dict(s.get("response") or self._failure(s.get("request_id","unknown"),s.get("correlation_id","unknown"),"Missing response","Missing response"));intent=r.get("intent")
  if intent:r=guardrail_engine.sanitize(r,str(intent))
  r["orchestration"]={"engine":"langgraph","graph":"TechAdminWorkflow","compiled":True,"terminal_stage":s.get("stage")};return {"response":r,"stage":"finalize_response"}
 def invoke(self,*,user_input,request_id=None,correlation_id=None,confirmed=False,requester_id=None,requester_role=None,source_channel="WORKFLOW"):
  initial={"user_input":user_input,"request_id":request_id or f"demo_{uuid4().hex[:12]}","correlation_id":correlation_id or f"corr_{uuid4().hex}","confirmed":confirmed,"requester_id":requester_id,"requester_role":requester_role,"stage":"start"};started=datetime.now(timezone.utc);response=None
  if not confirmed:open_request(initial["request_id"],user_input,requester_id,source_channel)
  try:
   response=self.graph.invoke(initial).get("response");
   if not isinstance(response,dict):raise RuntimeError("Graph returned no response")
   return response
  finally:close_request(initial["request_id"],response or {"success":False,"user_input":user_input,"error":"No response"},started_at=started,finished_at=datetime.now(timezone.utc))
 def execute(self,**kwargs):return self.invoke(**kwargs)
 def draw_mermaid(self):return self.graph.get_graph().draw_mermaid()
 @staticmethod
 def _rehome(tr):
  if not isinstance(tr,dict) or not isinstance(tr.get("result"),dict):return tr
  p=tr["result"].pop("_transient_password",None)
  if p:tr["result"]["password_token"]=password_vault.store(password=p,username=tr["result"].get("user_name") or "",employee_name=tr["result"].get("employee_name") or "",manager_name=tr["result"].get("manager_name") or "Not Available",manager_email=tr["result"].get("manager_email") or "Not Available")
  return tr
 @staticmethod
 def _base(s,e,message,error):return {"success":False,"request_id":s["request_id"],"correlation_id":s["correlation_id"],"user_input":s["user_input"],"intent":e.intent.value,"confidence":e.confidence,"explanation":e.explanation,"metadata":e.metadata.model_dump(mode="json"),"message":message,"error":error}
 @staticmethod
 def _failure(r,c,m,e):return {"success":False,"request_id":r,"correlation_id":c,"message":m,"error":e}
 @staticmethod
 def _guardrail_response(r,c,q,d,e=None):return {"success":False,"request_id":r,"correlation_id":c,"user_input":q,"intent":e.intent.value if e else None,"confidence":e.confidence if e else 0,"metadata":e.metadata.model_dump(mode="json") if e else {},"guardrail_blocked":d.blocked,"confirmation_required":d.needs_confirmation,"confirmation_prompt":d.confirmation_prompt,"message":d.message,"error":d.violations[0].code.value if d.violations else "guardrail_blocked"}
