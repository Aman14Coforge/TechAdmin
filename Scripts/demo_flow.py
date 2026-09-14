"""Complete TechAdmin MCP flow with guardrails and approval bridging."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any
from uuid import uuid4

from dotenv import load_dotenv
from loguru import logger

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
load_dotenv(PROJECT_ROOT / ".env", override=False)

from App.agents.identity_agent import IdentityAgent
from App.guardrails import guardrail_engine
from App.guardrails.engine import audit
from App.intent.unified_extractor import UnifiedIntentMetadataExtractor
from App.workflow.router import AgentRouter
from App.workflow.state import ExecutionBackend, IntentType


class DemoFlow:
    MINIMUM_INTENT_CONFIDENCE = 0.70

    def __init__(self) -> None:
        self.extractor = UnifiedIntentMetadataExtractor()
        self.router = AgentRouter()
        self.identity_agent = IdentityAgent()
        logger.info("DEMO_FLOW_INITIALIZED | extractor={} | router={} | agent={}", type(self.extractor).__name__, type(self.router).__name__, type(self.identity_agent).__name__)

    @staticmethod
    def _approval_required(intent: IntentType, backend: ExecutionBackend | None) -> bool:
        return (
            intent in {IntentType.REVOKE_ACCESS, IntentType.DELETE_USER}
            or (intent is IntentType.PASSWORD_RESET and backend == ExecutionBackend.SCRIPT)
        )

    def execute_flow(
        self,
        user_input: str,
        request_id: str | None = None,
        correlation_id: str | None = None,
        confirmed: bool = False,
        requester_id: str | None = None,
        requester_role: str | None = None,
    ) -> dict[str, Any]:
        query = user_input.strip() if isinstance(user_input, str) else ""
        request_id = request_id or f"demo_{uuid4().hex[:12]}"
        correlation_id = correlation_id or f"corr_{uuid4().hex}"

        if not query:
            return self._failure(request_id, correlation_id, "User input cannot be empty.", "Empty user input")

        input_decision = guardrail_engine.validate_input(query, request_id)
        if input_decision.blocked:
            return self._guardrail_response(request_id, correlation_id, query, input_decision)

        extraction = self.extractor.extract_all(query)
        if not extraction.success:
            return self._base_response(request_id, correlation_id, query, extraction, message=extraction.explanation, error=extraction.error)

        if extraction.confidence < self.MINIMUM_INTENT_CONFIDENCE:
            return self._base_response(request_id, correlation_id, query, extraction, message="The intent confidence is too low to continue safely.", error="Low intent confidence")

        decision = guardrail_engine.validate_request(
            intent=extraction.intent.value,
            metadata=extraction.metadata.model_dump(mode="json"),
            request_id=request_id,
            requester_id=requester_id,
            requester_role=requester_role,
            confirmed=confirmed,
        )
        if decision.blocked or decision.needs_confirmation:
            return self._guardrail_response(request_id, correlation_id, query, decision, extraction)

        # Trusted confirmation bridge. The LLM always keeps approval false.
        if confirmed and self._approval_required(extraction.intent, extraction.metadata.execution_backend):
            extraction = extraction.model_copy(
                update={
                    "metadata": extraction.metadata.model_copy(
                        update={"approval_granted": True}
                    )
                }
            )
            logger.warning(
                "TRUSTED_UI_APPROVAL_APPLIED | request_id={} | correlation_id={} | intent={} | username={} | group_name={}",
                request_id, correlation_id, extraction.intent.value,
                extraction.metadata.username, extraction.metadata.group_name,
            )

        try:
            routing = self.router.route(extraction.intent, extraction.metadata.model_dump(mode="json"))
        except ValueError as exc:
            return self._base_response(request_id, correlation_id, query, extraction, message=str(exc), error=type(exc).__name__)

        if routing.agent_type.value != "identity":
            response = self._base_response(request_id, correlation_id, query, extraction, message="Only the Identity Agent is implemented in this demo.", error="Agent unavailable")
            response["selected_agent"] = routing.agent_name
            return response

        try:
            agent_result = self.identity_agent.execute(
                operation=extraction.intent,
                metadata=extraction.metadata,
                request_id=request_id,
                correlation_id=correlation_id,
            )
        except Exception as exc:
            logger.exception("FLOW_AGENT_EXECUTION_FAILED | request_id={} | error_type={}", request_id, type(exc).__name__)
            response = self._base_response(request_id, correlation_id, query, extraction, message="Identity Agent execution failed.", error=type(exc).__name__)
            response["selected_agent"] = routing.agent_name
            return response

        clarification = agent_result.clarification_required
        tool_result = agent_result.tool_result.model_dump(mode="json") if agent_result.tool_result else None
        response = {
            "success": agent_result.success,
            "request_id": request_id,
            "correlation_id": correlation_id,
            "user_input": query,
            "intent": extraction.intent.value,
            "confidence": extraction.confidence,
            "explanation": extraction.explanation,
            "metadata": agent_result.metadata.model_dump(mode="json"),
            "validation": agent_result.validation.model_dump(mode="json"),
            "selected_agent": agent_result.selected_agent,
            "selected_mcp_server": None if clarification else self._mcp_server(extraction.intent),
            "selected_mcp_tool": None if clarification else self._mcp_tool(extraction.intent),
            "selected_tool": agent_result.selected_tool.value if agent_result.selected_tool else None,
            "tool_result": tool_result,
            "clarification_required": clarification,
            "clarification_question": agent_result.clarification_question,
            "message": agent_result.message,
            "error": agent_result.error,
        }

        if extraction.intent is IntentType.PASSWORD_RESET and agent_result.success:
            guardrail_engine.record_reset(guardrail_engine.target_identifier(extraction.metadata.model_dump(mode="json")) or "")

        audit("GUARDRAIL_OUTPUT", request_id, intent=extraction.intent.value, success=agent_result.success)
        return guardrail_engine.sanitize(response, extraction.intent.value)

    def _mcp_server(self, intent: IntentType) -> str | None:
        return self.identity_agent.mcp_client.SERVER_MODULES.get(intent.value)

    def _mcp_tool(self, intent: IntentType) -> str | None:
        return self.identity_agent.mcp_client.TOOL_NAMES.get(intent.value)

    @staticmethod
    def _base_response(request_id, correlation_id, query, extraction, *, message, error):
        return {
            "success": False, "request_id": request_id, "correlation_id": correlation_id,
            "user_input": query, "intent": extraction.intent.value,
            "confidence": extraction.confidence, "explanation": extraction.explanation,
            "metadata": extraction.metadata.model_dump(mode="json"), "validation": None,
            "selected_agent": None, "selected_mcp_server": None,
            "selected_mcp_tool": None, "selected_tool": None, "tool_result": None,
            "clarification_required": False, "clarification_question": None,
            "message": message, "error": error,
        }

    @staticmethod
    def _guardrail_response(request_id, correlation_id, query, decision, extraction=None):
        return {
            "success": False, "request_id": request_id, "correlation_id": correlation_id,
            "user_input": query,
            "intent": extraction.intent.value if extraction else None,
            "confidence": extraction.confidence if extraction else 0.0,
            "explanation": extraction.explanation if extraction else None,
            "metadata": extraction.metadata.model_dump(mode="json") if extraction else {},
            "validation": None, "selected_agent": None, "selected_mcp_server": None,
            "selected_mcp_tool": None, "selected_tool": None, "tool_result": None,
            "clarification_required": False, "clarification_question": None,
            "guardrail_action": decision.action.value,
            "guardrail_blocked": decision.blocked,
            "confirmation_required": decision.needs_confirmation,
            "confirmation_prompt": decision.confirmation_prompt,
            "guardrail_violations": [v.model_dump(mode="json") for v in decision.violations],
            "message": decision.message,
            "error": decision.violations[0].code.value if decision.violations else "guardrail_blocked",
        }

    @staticmethod
    def _failure(request_id, correlation_id, message, error):
        return {
            "success": False, "request_id": request_id, "correlation_id": correlation_id,
            "user_input": None, "intent": None, "confidence": 0.0,
            "explanation": None, "metadata": {}, "validation": None,
            "selected_agent": None, "selected_mcp_server": None,
            "selected_mcp_tool": None, "selected_tool": None, "tool_result": None,
            "clarification_required": False, "clarification_question": None,
            "message": message, "error": error,
        }
