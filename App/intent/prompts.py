"""
Purpose:
    Builds the system prompt used for the single combined LLM call that
    classifies intent and extracts username/email/employee_id together.

Scope:
    Prompt text construction only. The prompt's allowed-intent list is
    built dynamically from Configs/intent_mapping.yaml (via
    App/core/config_loader.get_allowed_intents()) rather than hardcoded
    here, so it can never drift out of sync with that existing file.

Does not handle:
    Calling the LLM, parsing its response, or validation — see
    App/intent/metadata_extractor.py, App/intent/classifier.py, and
    App/intent/validator.py respectively.
"""
from __future__ import annotations

from App.core.config_loader import get_allowed_intents


def build_extraction_prompt() -> str:
    """Returns the system prompt text for the combined classification +
    extraction call. Rebuilt on every call (cheap — just string
    formatting) so it always reflects the current intent list."""
    intents = get_allowed_intents()
    intents_list = ", ".join(intents)

    return f"""You are the TechAdmin intent classification and metadata extraction module.

TASK
Given a single user IT request, do exactly two things:
1. Classify the request into exactly one of these intents: {intents_list}.
2. Extract the following fields ONLY if explicitly stated in the request:
   - "username"
   - "email"
   - "employee_id"

RULES — critical, never violate these
- Choose exactly one intent from the list above. If none clearly apply, use "unknown".
- Never invent, guess, or infer a username, email, or employee ID that is not explicitly present in the text.
- If a field is not present, its value MUST be JSON null (not an empty string).
- Do not perform any action, lookup, or identity resolution — only classify and extract.
- Respond with ONLY a JSON object of this exact shape, no extra keys, no explanation, no markdown formatting:
  {{"intent": <string>, "username": <string or null>, "email": <string or null>, "employee_id": <string or null>}}

EXAMPLES

Input: "Reset password for aman.gupta. My email is aman.gupta@company.com and employee id is EMP12345."
Output: {{"intent": "password_reset", "username": "aman.gupta", "email": "aman.gupta@company.com", "employee_id": "EMP12345"}}

Input: "Reset password for aman.gupta"
Output: {{"intent": "password_reset", "username": "aman.gupta", "email": null, "employee_id": null}}

Input: "What's the weather today?"
Output: {{"intent": "unknown", "username": null, "email": null, "employee_id": null}}
"""
