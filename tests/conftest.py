"""
Purpose:
    Shared pytest fixtures for this module's test suite.

Scope:
    Provides FakeLLMClient (a deterministic stand-in implementing the
    same complete_json(system_prompt, user_prompt) -> dict contract the
    real Ollama/Gemini clients use) and AlwaysFailingLLMClient, plus
    fixtures built on top of them.

Does not handle:
    Any production code path — everything here exists only to make tests
    runnable without a live Ollama instance or a real Gemini API key.
"""
from __future__ import annotations

import re

import pytest

from App.core.llm_client import LLMInvocationError
from App.workflows.intent_node import build_intent_node

_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_EMPLOYEE_ID_RE = re.compile(r"\b(EMP\d{3,8})\b", re.IGNORECASE)
_USERNAME_RE = re.compile(r"\bfor\s+([a-zA-Z][\w.]*)")


class FakeLLMClient:
    """Rule-based stand-in for the real Ollama/Gemini clients — picks its
    canned response apart with regex instead of an actual model call."""

    def complete_json(self, system_prompt: str, user_prompt: str) -> dict:
        lowered = user_prompt.lower()
        intent = "password_reset" if "reset" in lowered and "password" in lowered else "unknown"

        email_match = _EMAIL_RE.search(user_prompt)
        employee_id_match = _EMPLOYEE_ID_RE.search(user_prompt)
        username_match = _USERNAME_RE.search(user_prompt)

        return {
            "intent": intent,
            "username": username_match.group(1).rstrip(".") if username_match else None,
            "email": email_match.group(0) if email_match else None,
            "employee_id": employee_id_match.group(1).upper() if employee_id_match else None,
        }


class AlwaysFailingLLMClient:
    """Simulates Ollama (or Gemini) being unavailable — every call
    raises."""

    def complete_json(self, system_prompt: str, user_prompt: str) -> dict:
        raise LLMInvocationError("simulated: connection refused")


@pytest.fixture
def fake_llm() -> FakeLLMClient:
    return FakeLLMClient()


@pytest.fixture
def intent_node(fake_llm):
    return build_intent_node(llm_client=fake_llm)
