"""
Purpose: Tests for App/workflows/state.py.
Scope: Confirms IntentState is a Pydantic model (not a TypedDict) — it
       validates types, applies defaults, and works as a LangGraph
       StateGraph schema.
"""
import pytest
from pydantic import BaseModel, ValidationError

from App.workflows.state import IntentState


def test_intent_state_is_a_pydantic_model():
    assert issubclass(IntentState, BaseModel)


def test_intent_state_defaults():
    state = IntentState()
    assert state.user_query == ""
    assert state.intent is None
    assert state.username is None
    assert state.email is None
    assert state.employee_id is None
    assert state.missing_fields == []
    assert state.is_valid is False
    assert state.error is None


def test_intent_state_accepts_valid_data():
    state = IntentState(
        user_query="Reset password for aman.gupta",
        intent="password_reset",
        username="aman.gupta",
        missing_fields=["email", "employee_id"],
        is_valid=False,
    )
    assert state.user_query == "Reset password for aman.gupta"
    assert state.missing_fields == ["email", "employee_id"]


def test_intent_state_rejects_wrong_type():
    with pytest.raises(ValidationError):
        IntentState(is_valid="not-a-bool-and-not-coercible")


def test_intent_state_missing_fields_defaults_are_independent_instances():
    """A classic mutable-default-argument bug — each instance must get
    its own list, not a list shared across all instances."""
    state_a = IntentState()
    state_b = IntentState()
    state_a.missing_fields.append("email")
    assert state_b.missing_fields == []


def test_intent_state_works_as_a_langgraph_state_schema():
    from langgraph.graph import END, START, StateGraph

    def node(state: IntentState):
        assert isinstance(state, IntentState)
        return {"intent": "password_reset"}

    graph = StateGraph(IntentState)
    graph.add_node("n", node)
    graph.add_edge(START, "n")
    graph.add_edge("n", END)
    compiled = graph.compile()

    result = compiled.invoke({"user_query": "Reset password for aman.gupta"})
    assert result["intent"] == "password_reset"
    assert result["user_query"] == "Reset password for aman.gupta"
