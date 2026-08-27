"""
Purpose:
    Robustly extracts a single JSON object from raw LLM text output that
    may contain reasoning, explanations, markdown fences, or other text
    around the actual JSON — observed in practice with local Qwen models
    even when the prompt asks for JSON-only output and Ollama's
    format="json" mode is requested.

Scope:
    Text -> dict extraction only, using a layered strategy: (1) the whole
    response is already valid JSON, (2) a fenced ```json ... ``` block
    contains valid JSON, (3) a balanced-brace scan finds a JSON object
    anywhere in the text, tolerating reasoning/prose before and after it.
    Does NOT validate the dict's shape against the expected schema — see
    App/schemas/extraction.py and App/intent/validator.py for that.

Does not handle:
    Calling the LLM or retry/fallback orchestration (see
    App/core/llm_client.py). The raw text is logged at DEBUG level only
    when extraction fails — it is never included in this module's return
    value, so it can never end up in the application's user-facing JSON.
"""
from __future__ import annotations

import json
import logging
import re

logger = logging.getLogger(__name__)

_FENCE_PATTERN = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)


class ResponseParsingError(Exception):
    """Raised when no JSON object could be extracted/parsed from the raw
    LLM response. Callers (App/core/llm_client.py's fallback orchestrator)
    treat this the same as a connection failure — it triggers retry/
    fallback rather than ever returning the raw text as if it were the
    result."""


def _find_balanced_json_objects(text: str) -> list[str]:
    """Scans `text` for every substring that is a syntactically balanced
    `{...}` block, respecting string literals (so a brace inside a quoted
    string — e.g. in a reasoning sentence — never throws off the count).
    Returns candidates in the order they appear in the text."""
    candidates: list[str] = []
    depth = 0
    start: int | None = None
    in_string = False
    escape = False

    for i, ch in enumerate(text):
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue

        if ch == '"':
            in_string = True
        elif ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            if depth > 0:
                depth -= 1
                if depth == 0 and start is not None:
                    candidates.append(text[start : i + 1])
                    start = None

    return candidates


def extract_json_object(raw_text: str) -> dict:
    """
    Layered extraction strategy, cheapest/most-likely-correct first:

    1. The whole (stripped) response is valid JSON on its own — the
       "clean" case, e.g. a well-behaved Gemini response.
    2. The response contains a ```json ... ``` (or plain ``` ... ```)
       fenced block whose contents parse as JSON.
    3. A balanced-brace scan finds one or more `{...}` substrings
       anywhere in the text — handling reasoning/explanations before
       and/or after the JSON, which is the Qwen behavior this exists
       for. Every candidate found is tried; a candidate containing an
       "intent" key is preferred over one that merely happens to parse
       (guards against an incidental `{...}` inside the model's prose).

    Raises ResponseParsingError if nothing usable is found anywhere in
    the text — never returns partial/guessed data.
    """
    if not isinstance(raw_text, str) or not raw_text.strip():
        raise ResponseParsingError("Raw LLM response was empty.")

    text = raw_text.strip()

    # 1. Whole response is already valid JSON.
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass

    # 2. Markdown-fenced JSON.
    for match in _FENCE_PATTERN.finditer(text):
        candidate = match.group(1).strip()
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed

    # 3. Balanced-brace scan across the whole text (handles reasoning
    #    before/after the JSON, with or without fences).
    parsed_candidates: list[dict] = []
    for candidate in _find_balanced_json_objects(text):
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            parsed_candidates.append(parsed)

    if parsed_candidates:
        for parsed in parsed_candidates:
            if "intent" in parsed:
                return parsed
        return parsed_candidates[0]

    # Only the raw text is logged (DEBUG level) — never returned.
    logger.debug("Failed to extract JSON from raw LLM response: %s", text)
    raise ResponseParsingError("No valid JSON object could be extracted from the model's response.")
