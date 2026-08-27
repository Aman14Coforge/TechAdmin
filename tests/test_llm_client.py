"""
Purpose: Tests for App/core/llm_client.py.
Scope: Ollama success path, parse-failure retry, Ollama-failure ->
       Gemini-fallback path, and the case where both fail.
       langchain_ollama.ChatOllama and
       langchain_google_genai.ChatGoogleGenerativeAI are monkeypatched to
       fakes, so no real Ollama instance or Gemini API key is needed.
"""
from __future__ import annotations

import langchain_google_genai
import langchain_ollama
import pytest

from App.core.llm_client import (
    GeminiLLMClient,
    LLMInvocationError,
    OllamaLLMClient,
    OllamaWithGeminiFallback,
)


class _FakeResponse:
    def __init__(self, content: str):
        self.content = content


class _SuccessModel:
    def __init__(self, **kwargs):
        self.kwargs = kwargs

    def invoke(self, prompt: str) -> _FakeResponse:
        return _FakeResponse(
            '{"intent": "password_reset", "username": "aman.gupta", "email": null, "employee_id": null}'
        )


class _FailingModel:
    def __init__(self, **kwargs):
        pass

    def invoke(self, prompt: str):
        raise RuntimeError("simulated connection failure")


class _FencedJsonModel:
    def __init__(self, **kwargs):
        pass

    def invoke(self, prompt: str) -> _FakeResponse:
        return _FakeResponse('```json\n{"intent": "unknown", "username": null, "email": null, "employee_id": null}\n```')


class _NoisyReasoningModel:
    """Simulates the exact behavior the underlying task is about — Qwen
    wrapping the JSON in reasoning/explanation text."""

    def __init__(self, **kwargs):
        pass

    def invoke(self, prompt: str) -> _FakeResponse:
        return _FakeResponse(
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


class _UnparseableModel:
    def __init__(self, **kwargs):
        pass

    def invoke(self, prompt: str) -> _FakeResponse:
        return _FakeResponse("I cannot help with that request, sorry.")


# --- OllamaLLMClient ------------------------------------------------------

def test_ollama_client_success_path(monkeypatch):
    monkeypatch.setattr(langchain_ollama, "ChatOllama", _SuccessModel)
    client = OllamaLLMClient(model="qwen3:14b", temperature=0)
    result = client.complete_json("system", "Reset password for aman.gupta")
    assert result["intent"] == "password_reset"
    assert result["username"] == "aman.gupta"


def test_ollama_client_strips_markdown_fences(monkeypatch):
    monkeypatch.setattr(langchain_ollama, "ChatOllama", _FencedJsonModel)
    client = OllamaLLMClient(model="qwen3:14b", temperature=0)
    result = client.complete_json("system", "user")
    assert result["intent"] == "unknown"


def test_ollama_client_extracts_json_from_reasoning_wrapped_response(monkeypatch):
    """Direct (no-retry) path — proves OllamaLLMClient.complete_json
    itself uses the robust parser, not naive json.loads."""
    monkeypatch.setattr(langchain_ollama, "ChatOllama", _NoisyReasoningModel)
    client = OllamaLLMClient(model="qwen3:14b", temperature=0)
    result = client.complete_json("system", "Reset password for aman.gupta")
    assert result == {
        "intent": "password_reset",
        "username": "aman.gupta",
        "email": "aman.gupta@company.com",
        "employee_id": "EMP12345",
    }


def test_ollama_client_failure_raises_llm_invocation_error(monkeypatch):
    monkeypatch.setattr(langchain_ollama, "ChatOllama", _FailingModel)
    client = OllamaLLMClient(model="qwen3:14b", temperature=0)
    with pytest.raises(LLMInvocationError):
        client.complete_json("system", "user")


# --- GeminiLLMClient --------------------------------------------------------

def test_gemini_client_success_path(monkeypatch):
    monkeypatch.setattr(langchain_google_genai, "ChatGoogleGenerativeAI", _SuccessModel)
    client = GeminiLLMClient(api_key="fake-key")
    result = client.complete_json("system", "user")
    assert result["intent"] == "password_reset"


def test_gemini_client_failure_raises_llm_invocation_error(monkeypatch):
    monkeypatch.setattr(langchain_google_genai, "ChatGoogleGenerativeAI", _FailingModel)
    client = GeminiLLMClient(api_key="fake-key")
    with pytest.raises(LLMInvocationError):
        client.complete_json("system", "user")


# --- OllamaWithGeminiFallback orchestration ---------------------------------
#
# Fakes here implement `complete_raw` (the interface the orchestrator
# actually calls), matching RawLLMClient / OllamaLLMClient / GeminiLLMClient.

def test_fallback_never_constructed_when_primary_succeeds():
    class _Primary:
        def complete_raw(self, system_prompt, user_prompt):
            return '{"intent": "password_reset"}'

    def _build_fallback():
        raise AssertionError("fallback must not be constructed when the primary call succeeds")

    client = OllamaWithGeminiFallback(primary=_Primary(), build_fallback=_build_fallback)
    result = client.complete_json("system", "user")
    assert result == {"intent": "password_reset"}


def test_connection_failure_goes_straight_to_fallback_without_retry():
    call_count = {"primary": 0}

    class _Primary:
        def complete_raw(self, system_prompt, user_prompt):
            call_count["primary"] += 1
            raise LLMInvocationError("ollama down")

    class _Fallback:
        def complete_raw(self, system_prompt, user_prompt):
            return '{"intent": "unknown"}'

    client = OllamaWithGeminiFallback(primary=_Primary(), build_fallback=lambda: _Fallback())
    result = client.complete_json("system", "user")

    assert result == {"intent": "unknown"}
    # Only one call — a connection failure is not worth retrying against
    # the same unreachable server.
    assert call_count["primary"] == 1


def test_parse_failure_retries_primary_once_before_falling_back():
    responses = iter(["not json at all", '{"intent": "password_reset"}'])

    class _Primary:
        def complete_raw(self, system_prompt, user_prompt):
            return next(responses)

    def _build_fallback():
        raise AssertionError("fallback must not be used when the retry succeeds")

    client = OllamaWithGeminiFallback(primary=_Primary(), build_fallback=_build_fallback)
    result = client.complete_json("system", "user")
    assert result == {"intent": "password_reset"}


def test_parse_failure_twice_falls_back_to_gemini():
    class _Primary:
        def complete_raw(self, system_prompt, user_prompt):
            return "still not json, sorry"

    class _Fallback:
        def complete_raw(self, system_prompt, user_prompt):
            return '{"intent": "password_reset", "username": "aman.gupta"}'

    client = OllamaWithGeminiFallback(primary=_Primary(), build_fallback=lambda: _Fallback())
    result = client.complete_json("system", "user")
    assert result == {"intent": "password_reset", "username": "aman.gupta"}


def test_error_when_primary_fails_and_no_fallback_configured():
    class _Primary:
        def complete_raw(self, system_prompt, user_prompt):
            raise LLMInvocationError("ollama down")

    client = OllamaWithGeminiFallback(primary=_Primary(), build_fallback=lambda: None)
    with pytest.raises(LLMInvocationError):
        client.complete_json("system", "user")


def test_error_when_both_primary_and_fallback_fail():
    class _Primary:
        def complete_raw(self, system_prompt, user_prompt):
            raise LLMInvocationError("ollama down")

    class _Fallback:
        def complete_raw(self, system_prompt, user_prompt):
            raise LLMInvocationError("gemini down too")

    client = OllamaWithGeminiFallback(primary=_Primary(), build_fallback=lambda: _Fallback())
    with pytest.raises(LLMInvocationError):
        client.complete_json("system", "user")


def test_error_when_both_parses_fail_end_to_end():
    """Neither Ollama's two attempts nor Gemini ever produce parseable
    JSON — must raise, never fabricate a result."""

    class _Primary:
        def complete_raw(self, system_prompt, user_prompt):
            return "I cannot help with that."

    class _Fallback:
        def complete_raw(self, system_prompt, user_prompt):
            return "Neither can I."

    client = OllamaWithGeminiFallback(primary=_Primary(), build_fallback=lambda: _Fallback())
    with pytest.raises(LLMInvocationError):
        client.complete_json("system", "user")


def test_end_to_end_with_real_ollama_client_returning_noisy_reasoning(monkeypatch):
    """Full stack: real OllamaLLMClient (mocked ChatOllama) wrapped in the
    fallback orchestrator, fed the exact kind of noisy response the task
    describes."""
    monkeypatch.setattr(langchain_ollama, "ChatOllama", _NoisyReasoningModel)
    primary = OllamaLLMClient(model="qwen3:14b", temperature=0)

    def _no_fallback():
        raise AssertionError("fallback must not be needed — the primary response is extractable")

    client = OllamaWithGeminiFallback(primary=primary, build_fallback=_no_fallback)
    result = client.complete_json("system", "Reset password for aman.gupta")

    assert result == {
        "intent": "password_reset",
        "username": "aman.gupta",
        "email": "aman.gupta@company.com",
        "employee_id": "EMP12345",
    }
