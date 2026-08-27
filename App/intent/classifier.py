"""
Purpose:
    Determines the final, controlled intent value from the raw LLM
    response, degrading anything outside the configured intent list
    (Configs/intent_mapping.yaml) to "unknown" rather than trusting
    free-form model output.

Scope:
    Intent value resolution only. This module makes no LLM call itself —
    it interprets the raw dict App/intent/metadata_extractor.py already
    obtained from the single combined LLM call.

Does not handle:
    Field extraction or validation.
"""
from __future__ import annotations

from typing import Any

from App.core.config_loader import get_allowed_intents


def classify_intent(raw_response: Any) -> str:
    """Never trusts the LLM's intent string outright — only a value that
    matches an entry already in Configs/intent_mapping.yaml (plus the
    built-in "unknown") is accepted."""
    allowed = get_allowed_intents()
    intent = raw_response.get("intent") if isinstance(raw_response, dict) else None
    if not isinstance(intent, str) or intent not in allowed:
        return "unknown"
    return intent
