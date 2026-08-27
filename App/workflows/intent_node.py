"""
Purpose:
    The LangGraph-compatible Intent Node: a single `state in, dict out`
    function combining LLM-based classification/extraction with
    deterministic validation.

Scope:
    Orchestrates App/intent/metadata_extractor.py, App/intent/classifier.py,
    App/schemas/extraction.py, and App/intent/validator.py into one
    LangGraph node function, using App/workflows/state.IntentState (a
    Pydantic model) as the state representation.

Does not handle:
    Building the full graph (StateGraph, edges, compilation), routing to
    any agent, or any action beyond returning structured, validated
    state. See the state transition flow below for exactly where this
    node's responsibility ends.

State transition flow:
    RECEIVED (user_query only)
        -> LLM call (Ollama, or Gemini if Ollama fails)
        -> raw {intent, username, email, employee_id}
        -> intent resolved against Configs/intent_mapping.yaml
        -> fields normalized through ExtractedFields
        -> missing_fields / is_valid computed deterministically
        -> COMPLETE (full result dict) or FAILED (result["error"] set)

Note on the dict-vs-model input:
    This node accepts `state` as either a plain dict (the shape every
    test and scripts/run_intent_cli.py already use, calling the node
    directly as a plain function) or an IntentState instance (the shape
    LangGraph passes in automatically when this node is registered into a
    compiled StateGraph(IntentState) — see the sandbox check in this
    project's build notes). Either way it's normalized to an IntentState
    instance first via IntentState.model_validate(), so the rest of the
    function can use plain attribute access instead of dict.get().
"""
from __future__ import annotations

from typing import Any

from App.core.llm_client import LLMClient, build_llm_client
from App.intent.classifier import classify_intent
from App.intent.metadata_extractor import MetadataExtractionError, extract_raw
from App.intent.validator import validate_fields
from App.schemas.extraction import ExtractedFields
from App.workflows.state import IntentState

_EMPTY_FIELDS = {"username": None, "email": None, "employee_id": None}


def build_intent_node(llm_client: LLMClient | None = None):
    """Returns a node function bound to the given (or default,
    Ollama-primary/Gemini-fallback) LLM client. Injecting `llm_client`
    lets tests swap in a fake without any network/model dependency."""
    client = llm_client or build_llm_client()

    def intent_node(state: IntentState | dict[str, Any]) -> dict[str, Any]:
        validated_state = state if isinstance(state, IntentState) else IntentState.model_validate(state)
        query = validated_state.user_query.strip()

        if not query:
            return {
                "error": "user_query is empty.",
                "intent": None,
                "is_valid": False,
                "missing_fields": [],
                **_EMPTY_FIELDS,
            }

        try:
            raw = extract_raw(client, query)
        except MetadataExtractionError as exc:
            return {
                "error": str(exc),
                "intent": None,
                "is_valid": False,
                "missing_fields": [],
                **_EMPTY_FIELDS,
            }

        intent = classify_intent(raw)
        fields = ExtractedFields.model_validate(
            {key: raw.get(key) for key in ("username", "email", "employee_id")}
        )
        missing_fields, is_valid = validate_fields(intent, fields)

        return {
            "error": None,
            "intent": intent,
            "username": fields.username,
            "email": fields.email,
            "employee_id": fields.employee_id,
            "missing_fields": missing_fields,
            "is_valid": is_valid,
        }

    return intent_node
