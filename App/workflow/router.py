from __future__ import annotations
from loguru import logger
from App.workflow.state import AgentType,IntentType,RoutingResult
class AgentRouter:
    INTENT_AGENT_MAPPING={
        IntentType.PASSWORD_RESET:AgentType.IDENTITY,IntentType.ACCOUNT_UNLOCK:AgentType.IDENTITY,IntentType.GRANT_ACCESS:AgentType.IDENTITY,IntentType.REVOKE_ACCESS:AgentType.IDENTITY,IntentType.GET_USER_DETAILS:AgentType.IDENTITY,IntentType.FAILED_LOGIN_INVESTIGATION:AgentType.IDENTITY,IntentType.CREATE_USER:AgentType.IDENTITY,IntentType.DELETE_USER:AgentType.IDENTITY,IntentType.CREATE_GROUP:AgentType.IDENTITY,IntentType.CREATE_VM:AgentType.IDENTITY,
        IntentType.PATCH_REPORT:AgentType.PATCH,IntentType.PATCH_TICKET:AgentType.PATCH,IntentType.PATCH_SCAN:AgentType.PATCH,
    }
    def route(self,intent:str|IntentType,metadata:dict|None=None)->RoutingResult:
        try: normalized=intent if isinstance(intent,IntentType) else IntentType(intent.strip().casefold())
        except (ValueError,AttributeError) as exc: raise ValueError(f"Unsupported intent: {intent}") from exc
        if normalized is IntentType.UNKNOWN: raise ValueError("The request does not match a supported TechAdmin operation.")
        agent=self.INTENT_AGENT_MAPPING.get(normalized)
        if agent is None: raise ValueError(f"No agent is registered for intent '{normalized.value}'.")
        result=RoutingResult(agent_name=f"{agent.value}_agent",agent_type=agent,routing_reason=f"Intent '{normalized.value}' maps to '{agent.value}_agent'.")
        logger.info("AGENT_ROUTED | intent={} | selected_agent={}",normalized.value,result.agent_name);return result
    def get_supported_agents(self)->list:return sorted({f"{a.value}_agent" for a in self.INTENT_AGENT_MAPPING.values()})
    def get_supported_intents(self)->list:return sorted(i.value for i in self.INTENT_AGENT_MAPPING)
