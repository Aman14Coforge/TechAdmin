"""Actual LangGraph orchestration for TechAdmin.

The graph owns every orchestration stage:
input guardrail -> extraction -> confidence -> request guardrail -> approval
bridge -> routing -> Identity Agent/MCP execution -> response -> sanitization.
No graph node calls DemoFlow.execute_flow().
"""
from __future__ import annotations

from typing import Any, Literal, TypedDict
from uuid import uuid4

from langgraph.graph import END, START, StateGraph
from loguru import logger

from App.agents.identity_agent import IdentityAgent
from App.guardrails import guardrail_engine
from App.guardrails.engine import audit
from App.intent.unified_extractor import UnifiedIntentMetadataExtractor
from App.services.password_vault import password_vault
from App.workflow.router import AgentRouter
from App.workflow.state import (
    AgentExecutionResult,
    ExecutionBackend,
    IntentType,
    RoutingResult,
    UnifiedExtractionResult,
)


class TechAdminGraphState(TypedDict, total=False):
    user_input: str
    request_id: str
    correlation_id: str
    confirmed: bool
    requester_id: str | None
    requester_role: str | None
    extraction: UnifiedExtractionResult | None
    routing: RoutingResult | None
    agent_result: AgentExecutionResult | None
    guardrail_decision: Any
    response: dict[str, Any] | None
    stage: str
    error: str | None


class TechAdminWorkflow:
    """Compiled production LangGraph using existing TechAdmin services."""

    MINIMUM_INTENT_CONFIDENCE = 0.70

    def __init__(
        self,
        *,
        extractor: UnifiedIntentMetadataExtractor | None = None,
        router: AgentRouter | None = None,
        identity_agent: IdentityAgent | None = None,
    ) -> None:
        self.extractor = extractor or UnifiedIntentMetadataExtractor()
        self.router = router or AgentRouter()
        self.identity_agent = identity_agent or IdentityAgent()
        self.graph = self._build_graph()
        logger.info(
            "LANGGRAPH_BUILD_COMPLETED | graph=TechAdminWorkflow | nodes={}",
            [
                "validate_input",
                "input_guardrail",
                "extract_request",
                "confidence_gate",
                "request_guardrail",
                "apply_trusted_approval",
                "route_agent",
                "execute_identity_agent",
                "build_agent_response",
                "finalize_response",
            ],
        )

    def _build_graph(self):
        builder = StateGraph(TechAdminGraphState)
        builder.add_node("validate_input", self._validate_input_node)
        builder.add_node("input_guardrail", self._input_guardrail_node)
        builder.add_node("extract_request", self._extract_request_node)
        builder.add_node("confidence_gate", self._confidence_gate_node)
        builder.add_node("request_guardrail", self._request_guardrail_node)
        builder.add_node("apply_trusted_approval", self._apply_trusted_approval_node)
        builder.add_node("route_agent", self._route_agent_node)
        builder.add_node("execute_identity_agent", self._execute_identity_agent_node)
        builder.add_node("build_agent_response", self._build_agent_response_node)
        builder.add_node("finalize_response", self._finalize_response_node)

        builder.add_edge(START, "validate_input")
        builder.add_conditional_edges(
            "validate_input", self._after_validate_input,
            {"continue": "input_guardrail", "finalize": "finalize_response"},
        )
        builder.add_conditional_edges(
            "input_guardrail", self._after_input_guardrail,
            {"continue": "extract_request", "finalize": "finalize_response"},
        )
        builder.add_conditional_edges(
            "extract_request", self._after_extraction,
            {"continue": "confidence_gate", "finalize": "finalize_response"},
        )
        builder.add_conditional_edges(
            "confidence_gate", self._after_confidence,
            {"continue": "request_guardrail", "finalize": "finalize_response"},
        )
        builder.add_conditional_edges(
            "request_guardrail", self._after_request_guardrail,
            {"continue": "apply_trusted_approval", "finalize": "finalize_response"},
        )
        builder.add_edge("apply_trusted_approval", "route_agent")
        builder.add_conditional_edges(
            "route_agent", self._after_routing,
            {"continue": "execute_identity_agent", "finalize": "finalize_response"},
        )
        builder.add_edge("execute_identity_agent", "build_agent_response")
        builder.add_edge("build_agent_response", "finalize_response")
        builder.add_edge("finalize_response", END)
        return builder.compile()

    @staticmethod
    def _has_response(state: TechAdminGraphState) -> bool:
        return isinstance(state.get("response"), dict)

    @classmethod
    def _after_validate_input(cls, state: TechAdminGraphState) -> Literal["continue", "finalize"]:
        return "finalize" if cls._has_response(state) else "continue"

    @classmethod
    def _after_input_guardrail(cls, state: TechAdminGraphState) -> Literal["continue", "finalize"]:
        return "finalize" if cls._has_response(state) else "continue"

    @classmethod
    def _after_extraction(cls, state: TechAdminGraphState) -> Literal["continue", "finalize"]:
        return "finalize" if cls._has_response(state) else "continue"

    @classmethod
    def _after_confidence(cls, state: TechAdminGraphState) -> Literal["continue", "finalize"]:
        return "finalize" if cls._has_response(state) else "continue"

    @classmethod
    def _after_request_guardrail(cls, state: TechAdminGraphState) -> Literal["continue", "finalize"]:
        return "finalize" if cls._has_response(state) else "continue"

    @classmethod
    def _after_routing(cls, state: TechAdminGraphState) -> Literal["continue", "finalize"]:
        return "finalize" if cls._has_response(state) else "continue"

    def _validate_input_node(self, state: TechAdminGraphState) -> dict[str, Any]:
        query = state.get("user_input")
        query = query.strip() if isinstance(query, str) else ""
        request_id = state.get("request_id") or f"demo_{uuid4().hex[:12]}"
        correlation_id = state.get("correlation_id") or f"corr_{uuid4().hex}"
        update: dict[str, Any] = {
            "user_input": query,
            "request_id": request_id,
            "correlation_id": correlation_id,
            "stage": "validate_input",
        }
        if not query:
            update["response"] = self._failure(
                request_id, correlation_id, "User input cannot be empty.", "Empty user input"
            )
        self._log_node("validate_input", state, update)
        return update

    def _input_guardrail_node(self, state: TechAdminGraphState) -> dict[str, Any]:
        decision = guardrail_engine.validate_input(state["user_input"], state["request_id"])
        update: dict[str, Any] = {"guardrail_decision": decision, "stage": "input_guardrail"}
        if decision.blocked:
            update["response"] = self._guardrail_response(
                state["request_id"], state["correlation_id"], state["user_input"], decision
            )
        self._log_node("input_guardrail", state, update)
        return update

    def _extract_request_node(self, state: TechAdminGraphState) -> dict[str, Any]:
        extraction = self.extractor.extract_all(state["user_input"])
        update: dict[str, Any] = {"extraction": extraction, "stage": "extract_request"}
        if not extraction.success:
            update["response"] = self._base_response(
                state["request_id"], state["correlation_id"], state["user_input"],
                extraction, message=extraction.explanation, error=extraction.error,
            )
        self._log_node("extract_request", state, update)
        return update

    def _confidence_gate_node(self, state: TechAdminGraphState) -> dict[str, Any]:
        extraction = state["extraction"]
        update: dict[str, Any] = {"stage": "confidence_gate"}
        if extraction is None:
            update["response"] = self._failure(
                state["request_id"], state["correlation_id"],
                "Request extraction is unavailable.", "Extraction unavailable",
            )
        elif extraction.confidence < self.MINIMUM_INTENT_CONFIDENCE:
            update["response"] = self._base_response(
                state["request_id"], state["correlation_id"], state["user_input"],
                extraction, message="The intent confidence is too low to continue safely.",
                error="Low intent confidence",
            )
        self._log_node("confidence_gate", state, update)
        return update

    def _request_guardrail_node(self, state: TechAdminGraphState) -> dict[str, Any]:
        extraction = state["extraction"]
        if extraction is None:
            raise RuntimeError("Extraction missing before request guardrail")
        decision = guardrail_engine.validate_request(
            intent=extraction.intent.value,
            metadata=extraction.metadata.model_dump(mode="json"),
            request_id=state["request_id"],
            requester_id=state.get("requester_id"),
            requester_role=state.get("requester_role"),
            confirmed=bool(state.get("confirmed", False)),
        )
        update: dict[str, Any] = {"guardrail_decision": decision, "stage": "request_guardrail"}
        if decision.blocked or decision.needs_confirmation:
            update["response"] = self._guardrail_response(
                state["request_id"], state["correlation_id"], state["user_input"],
                decision, extraction,
            )
        self._log_node("request_guardrail", state, update)
        return update

    def _apply_trusted_approval_node(self, state: TechAdminGraphState) -> dict[str, Any]:
        extraction = state["extraction"]
        if extraction is None:
            raise RuntimeError("Extraction missing before approval bridge")
        if bool(state.get("confirmed")) and self._approval_required(
            extraction.intent, extraction.metadata.execution_backend
        ):
            extraction = extraction.model_copy(
                update={
                    "metadata": extraction.metadata.model_copy(
                        update={"approval_granted": True}
                    )
                }
            )
            logger.warning(
                "TRUSTED_UI_APPROVAL_APPLIED | request_id={} | correlation_id={} | intent={} | username={} | group_name={}",
                state["request_id"], state["correlation_id"], extraction.intent.value,
                extraction.metadata.username, extraction.metadata.group_name,
            )
        update = {"extraction": extraction, "stage": "apply_trusted_approval"}
        self._log_node("apply_trusted_approval", state, update)
        return update

    def _route_agent_node(self, state: TechAdminGraphState) -> dict[str, Any]:
        extraction = state["extraction"]
        if extraction is None:
            raise RuntimeError("Extraction missing before routing")
        update: dict[str, Any] = {"stage": "route_agent"}
        try:
            routing = self.router.route(
                extraction.intent, extraction.metadata.model_dump(mode="json")
            )
            update["routing"] = routing
            if routing.agent_type.value != "identity":
                response = self._base_response(
                    state["request_id"], state["correlation_id"], state["user_input"],
                    extraction, message="Only the Identity Agent is implemented in this deployment.",
                    error="Agent unavailable",
                )
                response["selected_agent"] = routing.agent_name
                update["response"] = response
        except ValueError as exc:
            update["response"] = self._base_response(
                state["request_id"], state["correlation_id"], state["user_input"],
                extraction, message=str(exc), error=type(exc).__name__,
            )
        self._log_node("route_agent", state, update)
        return update

    def _execute_identity_agent_node(self, state: TechAdminGraphState) -> dict[str, Any]:
        extraction = state["extraction"]
        if extraction is None:
            raise RuntimeError("Extraction missing before agent execution")
        try:
            result = self.identity_agent.execute(
                operation=extraction.intent,
                metadata=extraction.metadata,
                request_id=state["request_id"],
                correlation_id=state["correlation_id"],
            )
            update = {"agent_result": result, "stage": "execute_identity_agent"}
        except Exception as exc:
            logger.exception(
                "LANGGRAPH_AGENT_EXECUTION_FAILED | request_id={} | error_type={}",
                state["request_id"], type(exc).__name__,
            )
            response = self._base_response(
                state["request_id"], state["correlation_id"], state["user_input"],
                extraction, message="Identity Agent execution failed.", error=type(exc).__name__,
            )
            routing = state.get("routing")
            response["selected_agent"] = routing.agent_name if routing else "identity_agent"
            update = {"response": response, "stage": "execute_identity_agent"}
        self._log_node("execute_identity_agent", state, update)
        return update

    def _build_agent_response_node(self, state: TechAdminGraphState) -> dict[str, Any]:
        if self._has_response(state):
            return {"stage": "build_agent_response"}
        extraction = state["extraction"]
        agent_result = state["agent_result"]
        if extraction is None or agent_result is None:
            return {
                "stage": "build_agent_response",
                "response": self._failure(
                    state["request_id"], state["correlation_id"],
                    "Agent result is unavailable.", "Agent result unavailable",
                ),
            }
        clarification = agent_result.clarification_required
        tool_result = (
            agent_result.tool_result.model_dump(mode="json")
            if agent_result.tool_result else None
        )
        tool_result = self._rehome_transient_password(tool_result)
        response = {
            "success": agent_result.success,
            "request_id": state["request_id"],
            "correlation_id": state["correlation_id"],
            "user_input": state["user_input"],
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
            target = guardrail_engine.target_identifier(
                extraction.metadata.model_dump(mode="json")
            ) or ""
            guardrail_engine.record_reset(target)
        audit(
            "GUARDRAIL_OUTPUT", state["request_id"],
            intent=extraction.intent.value, success=agent_result.success,
        )
        update = {"response": response, "stage": "build_agent_response"}
        self._log_node("build_agent_response", state, update)
        return update

    def _finalize_response_node(self, state: TechAdminGraphState) -> dict[str, Any]:
        response = dict(state.get("response") or self._failure(
            state.get("request_id") or "unknown",
            state.get("correlation_id") or "unknown",
            "Workflow completed without a response.", "Missing workflow response",
        ))
        intent = response.get("intent")
        if intent:
            response = guardrail_engine.sanitize(response, str(intent))
        response["orchestration"] = {
            "engine": "langgraph",
            "graph": "TechAdminWorkflow",
            "compiled": True,
            "terminal_stage": state.get("stage"),
        }
        logger.info(
            "LANGGRAPH_NODE_COMPLETED | node=finalize_response | request_id={} | intent={} | success={}",
            response.get("request_id"), response.get("intent"), response.get("success"),
        )
        return {"response": response, "stage": "finalize_response"}

    def invoke(
        self,
        *,
        user_input: str,
        request_id: str | None = None,
        correlation_id: str | None = None,
        confirmed: bool = False,
        requester_id: str | None = None,
        requester_role: str | None = None,
    ) -> dict[str, Any]:
        initial: TechAdminGraphState = {
            "user_input": user_input,
            "request_id": request_id or f"demo_{uuid4().hex[:12]}",
            "correlation_id": correlation_id or f"corr_{uuid4().hex}",
            "confirmed": bool(confirmed),
            "requester_id": requester_id,
            "requester_role": requester_role,
            "extraction": None,
            "routing": None,
            "agent_result": None,
            "guardrail_decision": None,
            "response": None,
            "stage": "start",
            "error": None,
        }
        logger.info(
            "LANGGRAPH_INVOKE_STARTED | request_id={} | correlation_id={} | confirmed={}",
            initial["request_id"], initial["correlation_id"], initial["confirmed"],
        )
        final_state = self.graph.invoke(initial)
        response = final_state.get("response")
        if not isinstance(response, dict):
            raise RuntimeError("LangGraph completed without a dictionary response.")
        logger.info(
            "LANGGRAPH_INVOKE_COMPLETED | request_id={} | correlation_id={} | intent={} | success={}",
            response.get("request_id"), response.get("correlation_id"),
            response.get("intent"), response.get("success"),
        )
        return response

    def execute(self, **kwargs: Any) -> dict[str, Any]:
        """Compatibility alias for callers that use execute()."""
        return self.invoke(**kwargs)

    def draw_mermaid(self) -> str:
        return self.graph.get_graph().draw_mermaid()

    @staticmethod
    def _approval_required(intent: IntentType, backend: ExecutionBackend | None) -> bool:
        return (
            intent in {IntentType.REVOKE_ACCESS, IntentType.DELETE_USER}
            or (intent is IntentType.PASSWORD_RESET and backend == ExecutionBackend.SCRIPT)
        )

    @staticmethod
    def _rehome_transient_password(tool_result: dict[str, Any] | None):
        if not isinstance(tool_result, dict):
            return tool_result
        result = tool_result.get("result")
        if not isinstance(result, dict):
            return tool_result
        password = result.pop("_transient_password", None)
        if not password:
            return tool_result
        result["password_token"] = password_vault.store(
            password=password,
            username=result.get("user_name") or result.get("user_principal_name") or "",
            employee_name=result.get("employee_name") or "",
            manager_name=result.get("manager_name") or "Not Available",
            manager_email=result.get("manager_email") or "Not Available",
        )
        return tool_result

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

    @staticmethod
    def _log_node(node: str, state: TechAdminGraphState, update: dict[str, Any]) -> None:
        logger.info(
            "LANGGRAPH_NODE_COMPLETED | node={} | request_id={} | correlation_id={} | terminal={}",
            node, state.get("request_id"), state.get("correlation_id"),
            isinstance(update.get("response"), dict),
        )
