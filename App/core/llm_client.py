"""
Purpose:
    LLM invocation layer for intent classification + metadata extraction.
    Wraps langchain_ollama.ChatOllama as the primary model (configured
    entirely from the existing, unmodified Configs/llm_config.yaml) and
    langchain_google_genai.ChatGoogleGenerativeAI as a fallback that is
    constructed and called ONLY if the primary path fails.

Scope:
    Two layers:
    - OllamaLLMClient / GeminiLLMClient: raw model invocation
      (`complete_raw`) plus a convenience `complete_json` that runs the
      raw response through App/core/response_parser.py with no retry
      logic — useful for direct/isolated testing of each provider.
    - OllamaWithGeminiFallback: the actual orchestrator used by the rest
      of the app. Implements the required flow —

          Ollama raw call
              -> parse/extract JSON
              -> parsed & valid?  YES -> return it
                                  NO (parse failure) -> ONE retry against
                                       Ollama with a corrective prompt
                                       -> still fails -> Gemini fallback
                                  NO (connection/timeout failure) -> go
                                       straight to Gemini fallback (no
                                       point retrying an unreachable
                                       server)
              -> Gemini also fails/unavailable -> raise a clear error,
                 never fabricate a result.

Does not handle:
    Prompt content (see App/intent/prompts.py) or schema/field validation
    (see App/schemas/extraction.py, App/intent/validator.py). Raw model
    text is never returned from `complete_json` on any of these classes —
    only a parsed dict, or a raised error.
"""
from __future__ import annotations

import logging
import os
from typing import Protocol

from App.core.config_loader import get_gemini_api_key, load_llm_config
from App.core.response_parser import ResponseParsingError, extract_json_object

logger = logging.getLogger(__name__)

_RETRY_SUFFIX = (
    "\n\nYour previous response could not be parsed as JSON. "
    "Respond again with ONLY the JSON object and nothing else — "
    "no reasoning, no explanation, no markdown formatting."
)


class LLMInvocationError(Exception):
    """Raised when a model call fails outright (connection error, timeout)
    or — for `OllamaWithGeminiFallback.complete_json` specifically — when
    both the primary and fallback paths have been exhausted (including
    parse failures). Callers treat this as a controlled failure, never
    letting it crash the request or fabricate a result."""


class RawLLMClient(Protocol):
    """A model that can produce raw text — no parsing performed here."""

    def complete_raw(self, system_prompt: str, user_prompt: str) -> str: ...


class LLMClient(Protocol):
    """A model (or orchestrator) that returns an already-parsed dict —
    this is the contract App/intent/metadata_extractor.py depends on."""

    def complete_json(self, system_prompt: str, user_prompt: str) -> dict: ...


class OllamaLLMClient:
    """Primary model — local Ollama, configured entirely from the
    existing Configs/llm_config.yaml (provider/model_name/temperature/
    top_p/timeout). That file is never modified; its values are simply
    read and passed through here."""

    def __init__(self, model: str, temperature: float, top_p: float | None = None, timeout: int | None = None):
        from langchain_ollama import ChatOllama

        kwargs: dict = {"model": model, "temperature": temperature, "format": "json"}
        if top_p is not None:
            kwargs["top_p"] = top_p
        if timeout is not None:
            # ChatOllama has no direct `timeout` field; the underlying
            # HTTP client accepts it through client_kwargs.
            kwargs["client_kwargs"] = {"timeout": timeout}
        self._llm = ChatOllama(**kwargs)

    def complete_raw(self, system_prompt: str, user_prompt: str) -> str:
        prompt = f"{system_prompt}\n\nUser Request:\n{user_prompt}"
        try:
            response = self._llm.invoke(prompt)
        except Exception as exc:  # noqa: BLE001 - deliberate containment boundary
            raise LLMInvocationError(f"Ollama request failed: {exc}") from exc
        return response.content

    def complete_json(self, system_prompt: str, user_prompt: str) -> dict:
        """Direct raw-call + parse, no retry. The retry/fallback policy
        lives in OllamaWithGeminiFallback, not here."""
        return extract_json_object(self.complete_raw(system_prompt, user_prompt))


class GeminiLLMClient:
    """Fallback model — only constructed/used when Ollama fails.

    There is no `fallback:` section in the existing Configs/llm_config.yaml
    (that file is left unmodified per project instructions), so the model
    name/temperature/timeout default below and can be overridden via
    GEMINI_MODEL / GEMINI_TEMPERATURE / GEMINI_TIMEOUT environment
    variables if needed. The API key is always sourced from the
    environment — never hardcoded, never read from YAML."""

    def __init__(self, api_key: str, model: str = "gemini-2.5-flash", temperature: float = 0.0, timeout: int | None = None):
        from langchain_google_genai import ChatGoogleGenerativeAI

        kwargs: dict = {"model": model, "temperature": temperature, "google_api_key": api_key}
        if timeout is not None:
            kwargs["timeout"] = timeout
        self._llm = ChatGoogleGenerativeAI(**kwargs)

    def complete_raw(self, system_prompt: str, user_prompt: str) -> str:
        prompt = f"{system_prompt}\n\nUser Request:\n{user_prompt}"
        try:
            response = self._llm.invoke(prompt)
        except Exception as exc:  # noqa: BLE001 - deliberate containment boundary
            raise LLMInvocationError(f"Gemini request failed: {exc}") from exc
        return response.content

    def complete_json(self, system_prompt: str, user_prompt: str) -> dict:
        return extract_json_object(self.complete_raw(system_prompt, user_prompt))


class OllamaWithGeminiFallback:
    """
    The orchestrator actually used by the rest of the app (injected as
    `llm_client` into App/workflows/intent_node.py). Implements:

        Ollama raw call
            connection/timeout failure -> Gemini fallback directly
            success -> parse
                parses & is a usable JSON object -> return it
                fails to parse -> ONE retry against Ollama with a
                    corrective prompt
                        retry parses -> return it
                        retry also fails/errors -> Gemini fallback
        Gemini fallback (only reached above)
            not configured (no GEMINI_API_KEY) -> raise LLMInvocationError
            fails (connection or parse) -> raise LLMInvocationError
            succeeds -> return parsed result

    Gemini is constructed lazily via `build_fallback()` — only if/when
    actually needed — so a missing GEMINI_API_KEY never matters on the
    normal, Ollama-succeeds path, and Gemini is never called alongside
    Ollama for a request Ollama already answered.
    """

    def __init__(self, primary: RawLLMClient, build_fallback):
        self._primary = primary
        self._build_fallback = build_fallback  # callable -> RawLLMClient | None

    def complete_json(self, system_prompt: str, user_prompt: str) -> dict:
        primary_exc: Exception

        try:
            raw = self._primary.complete_raw(system_prompt, user_prompt)
        except LLMInvocationError as conn_exc:
            # Connection/timeout failure — retrying the same unreachable
            # server won't help; go straight to the fallback.
            primary_exc = conn_exc
        else:
            try:
                return extract_json_object(raw)
            except ResponseParsingError as parse_exc:
                logger.debug("Primary response failed to parse; retrying once. Raw response: %s", raw)
                try:
                    retry_raw = self._primary.complete_raw(system_prompt, user_prompt + _RETRY_SUFFIX)
                    return extract_json_object(retry_raw)
                except (LLMInvocationError, ResponseParsingError) as retry_exc:
                    primary_exc = retry_exc

        fallback = self._build_fallback()
        if fallback is None:
            raise LLMInvocationError(
                f"Ollama failed and no Gemini fallback is configured "
                f"(set GEMINI_API_KEY to enable it): {primary_exc}"
            ) from primary_exc

        try:
            fallback_raw = fallback.complete_raw(system_prompt, user_prompt)
            return extract_json_object(fallback_raw)
        except (LLMInvocationError, ResponseParsingError) as fallback_exc:
            raise LLMInvocationError(
                f"Ollama failed ({primary_exc}) and Gemini fallback also failed ({fallback_exc})."
            ) from fallback_exc


def build_llm_client() -> OllamaWithGeminiFallback:
    """Assembles the primary/fallback client from the existing
    Configs/llm_config.yaml plus GEMINI_API_KEY from the environment."""
    config = load_llm_config()
    llm_cfg = config.get("llm", {}) or {}

    primary = OllamaLLMClient(
        model=llm_cfg.get("model_name", "qwen3:14b"),
        temperature=llm_cfg.get("temperature", 0),
        top_p=llm_cfg.get("top_p"),
        timeout=llm_cfg.get("timeout"),
    )

    def _build_fallback() -> RawLLMClient | None:
        api_key = get_gemini_api_key()
        if not api_key:
            return None
        return GeminiLLMClient(
            api_key=api_key,
            model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
            temperature=float(os.getenv("GEMINI_TEMPERATURE", "0.0")),
            timeout=int(os.getenv("GEMINI_TIMEOUT", "60")),
        )

    return OllamaWithGeminiFallback(primary=primary, build_fallback=_build_fallback)
