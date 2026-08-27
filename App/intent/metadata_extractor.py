"""
Purpose:
    Makes the single LLM call that classifies intent and extracts
    username/email/employee_id together, and returns the raw parsed JSON
    response for App/intent/classifier.py and App/schemas/extraction.py
    to interpret.

Scope:
    LLM invocation + raw response shape checking only. One call per query
    — intent and fields are extracted together rather than with separate
    calls, since they come from the same piece of text and splitting them
    would only double LLM cost without adding accuracy.

Does not handle:
    Deciding whether the intent is valid (see App/intent/classifier.py),
    field-level normalization (see App/schemas/extraction.py), or
    missing-field validation (see App/intent/validator.py).
"""
from __future__ import annotations

from App.core.llm_client import LLMClient, LLMInvocationError
from App.intent.prompts import build_extraction_prompt


class MetadataExtractionError(Exception):
    """Controlled error for an empty query or an LLM call that fails —
    including exhausting the Ollama -> Gemini fallback chain."""


def extract_raw(llm_client: LLMClient, user_query: str) -> dict:
    if not user_query or not user_query.strip():
        raise MetadataExtractionError("user_query is empty.")

    system_prompt = build_extraction_prompt()
    try:
        raw = llm_client.complete_json(system_prompt, user_query)
    except LLMInvocationError as exc:
        raise MetadataExtractionError(str(exc)) from exc

    if not isinstance(raw, dict):
        raise MetadataExtractionError(f"LLM response was not a JSON object: {raw!r}")
    return raw
