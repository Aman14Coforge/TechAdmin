"""
Purpose: End-to-end tests for App/workflows/intent_node.py.
Scope: The full classify -> extract -> validate pipeline via the node
       function, plus a check that the node drops into a real LangGraph
       StateGraph correctly.
"""
from __future__ import annotations

from App.core.llm_client import LLMInvocationError
from App.workflows.intent_node import build_intent_node


def test_node_all_fields_present(intent_node):
    result = intent_node(
        {"user_query": "Reset password for aman.gupta. My email is aman.gupta@company.com and employee id is EMP12345."}
    )
    assert result == {
        "error": None,
        "intent": "password_reset",
        "username": "aman.gupta",
        "email": "aman.gupta@company.com",
        "employee_id": "EMP12345",
        "missing_fields": [],
        "is_valid": True,
    }


def test_node_missing_fields_reported(intent_node):
    result = intent_node({"user_query": "Reset password for aman.gupta"})
    assert result["intent"] == "password_reset"
    assert result["username"] == "aman.gupta"
    assert set(result["missing_fields"]) == {"email", "employee_id"}
    assert result["is_valid"] is False


def test_node_unknown_intent(intent_node):
    result = intent_node({"user_query": "What's the weather today?"})
    assert result["intent"] == "unknown"
    assert result["missing_fields"] == []
    assert result["is_valid"] is True  # no mandatory-field list defined for "unknown"


def test_node_empty_query_returns_controlled_error(intent_node):
    result = intent_node({"user_query": ""})
    assert result["error"] is not None
    assert result["intent"] is None


def test_node_llm_failure_returns_controlled_error():
    class _AlwaysFails:
        def complete_json(self, system_prompt, user_prompt):
            raise LLMInvocationError("simulated failure")

    node = build_intent_node(llm_client=_AlwaysFails())
    result = node({"user_query": "Reset password for aman.gupta"})
    assert result["error"] is not None
    assert result["intent"] is None


def test_node_accepts_an_intent_state_instance_directly(fake_llm):
    """The node must work whether called with a plain dict (as every
    other test does) or an already-constructed IntentState instance
    (the shape LangGraph itself passes in via a compiled StateGraph)."""
    from App.workflows.state import IntentState

    node = build_intent_node(llm_client=fake_llm)
    state = IntentState(user_query="Reset password for aman.gupta")
    result = node(state)
    assert result["intent"] == "password_reset"
    assert result["username"] == "aman.gupta"


def test_node_is_compatible_with_a_real_langgraph_state_graph(intent_node):
    """Proves the node function has the right shape to be registered into
    an actual StateGraph by a future developer."""
    from langgraph.graph import END, START, StateGraph

    from App.workflows.state import IntentState

    graph = StateGraph(IntentState)
    graph.add_node("intent", intent_node)
    graph.add_edge(START, "intent")
    graph.add_edge("intent", END)
    compiled = graph.compile()

    result = compiled.invoke({"user_query": "Reset password for aman.gupta, employee id EMP12345"})
    assert result["intent"] == "password_reset"
    assert result["username"] == "aman.gupta"
    assert result["employee_id"] == "EMP12345"
    assert "email" in result["missing_fields"]


def test_node_output_contains_only_clean_json_never_raw_reasoning():
    """End-to-end proof (LLM client -> parser -> schema -> validator ->
    node) that a Qwen-style response wrapped in reasoning/explanation
    text produces ONLY the final structured result — no reasoning, no
    markdown, no raw text anywhere in the node's output."""
    from App.core.llm_client import OllamaWithGeminiFallback

    class _NoisyPrimary:
        def complete_raw(self, system_prompt, user_prompt):
            return (
                "Let me analyze this request carefully.\n\n"
                "The requested operation is a password reset.\n\n"
                "{\n"
                '  "intent": "password_reset",\n'
                '  "username": "aman.gupta",\n'
                '  "email": "aman.gupta@company.com",\n'
                '  "employee_id": "EMP12345"\n'
                "}\n\n"
                "This contains all required information."
            )

    def _no_fallback_needed():
        raise AssertionError("fallback must not be needed — the primary response is extractable")

    node = build_intent_node(
        llm_client=OllamaWithGeminiFallback(primary=_NoisyPrimary(), build_fallback=_no_fallback_needed)
    )

    result = node({"user_query": "Reset password for aman.gupta"})

    assert result == {
        "error": None,
        "intent": "password_reset",
        "username": "aman.gupta",
        "email": "aman.gupta@company.com",
        "employee_id": "EMP12345",
        "missing_fields": [],
        "is_valid": True,
    }

    # Belt-and-suspenders: none of the reasoning text leaked through
    # anywhere in the final result.
    result_text = str(result)
    assert "Let me analyze" not in result_text
    assert "carefully" not in result_text
    assert "This contains all required information" not in result_text
