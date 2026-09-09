"""
Unified Intent and Metadata Extractor Module

Purpose:
    Extract intent and metadata in one timed Ollama invocation.

Responsibilities:
    - Classify one supported TechAdmin intent.
    - Extract identity and infrastructure metadata.
    - Detect an explicitly requested API or script backend.
    - Parse clean, fenced, or reasoning-wrapped JSON.
    - Validate the normalized result through Pydantic.
    - Derive username from email when username is absent.
    - Measure and log Ollama execution time.
    - Return controlled failure results.

Security:
    - The LLM is never trusted to grant approval.
    - Passwords are never accepted from LLM output.
    - API/script backend is selected only from explicit user wording or a
      controlled LLM value.
"""

from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime
from typing import Any

from langchain_ollama import ChatOllama
from loguru import logger
from pydantic import ValidationError

from App.intent.prompts import UNIFIED_EXTRACTION_PROMPT
from App.workflow.state import (
    ExecutionBackend,
    IdentityMetadata,
    IntentType,
    UnifiedExtractionResult,
)


class UnifiedIntentMetadataExtractor:
    """Extract intent and metadata using one Ollama call."""

    STRING_METADATA_FIELDS: tuple[str, ...] = (
        "username",
        "user_id",
        "email",
        "employee_number",
        "group_name",
        "time_window",
        "username_source",
        "first_name",
        "last_name",
        "department",
        "target_ou",
        "description",
        "target_host",
        "vm_name",
        "vswitch_name",
        "ip_address",
        "subnet",
        "gateway",
        "dns",
        "hostname",
        "domain",
        "domain_user",
    )

    SCRIPT_BACKEND_PATTERNS: tuple[str, ...] = (
        r"\bvia\s+(?:a\s+|the\s+)?scripts?\b",
        r"\busing\s+(?:a\s+|the\s+)?scripts?\b",
        r"\bthrough\s+(?:a\s+|the\s+)?scripts?\b",
        r"\bwith\s+(?:a\s+|the\s+)?scripts?\b",
        r"\bvia\s+powershell\b",
        r"\busing\s+powershell\b",
        r"\bthrough\s+powershell\b",
        r"\bwith\s+powershell\b",
        r"\bpowershell\s+scripts?\b",
    )

    API_BACKEND_PATTERNS: tuple[str, ...] = (
        r"\bvia\s+(?:an?\s+|the\s+)?api\b",
        r"\busing\s+(?:an?\s+|the\s+)?api\b",
        r"\bthrough\s+(?:an?\s+|the\s+)?api\b",
        r"\bwith\s+(?:an?\s+|the\s+)?api\b",
        r"\bvia\s+microsoft\s+graph\b",
        r"\busing\s+microsoft\s+graph\b",
        r"\bthrough\s+microsoft\s+graph\b",
        r"\bwith\s+microsoft\s+graph\b",
        r"\bmicrosoft\s+graph\s+api\b",
    )

    def __init__(
        self,
        model_name: str | None = None,
        ollama_host: str | None = None,
    ) -> None:
        self.model_name = model_name or os.getenv(
            "MODEL_NAME",
            "qwen3:14b",
        )

        self.ollama_host = ollama_host or os.getenv(
            "OLLAMA_HOST",
            "http://localhost:11434",
        )

        self.llm: ChatOllama | None = None
        self.initialization_error: str | None = None

        try:
            self.llm = ChatOllama(
                model=self.model_name,
                base_url=self.ollama_host,
                temperature=0,
                format="json",
            )

            logger.info(
                "UnifiedIntentMetadataExtractor initialized | "
                "model={} | ollama_host={}",
                self.model_name,
                self.ollama_host,
            )

        except Exception as exc:
            self.initialization_error = type(exc).__name__

            logger.exception(
                "UNIFIED_EXTRACTOR_INITIALIZATION_FAILED | "
                "model={} | ollama_host={} | error_type={}",
                self.model_name,
                self.ollama_host,
                self.initialization_error,
            )

    def extract_all(
        self,
        user_input: str,
    ) -> UnifiedExtractionResult:
        """Extract and validate intent and metadata from one user request."""

        normalized_input = self._normalize_user_input(user_input)

        if not normalized_input:
            logger.warning(
                "UNIFIED_EXTRACTION_REJECTED | reason=empty_user_input"
            )
            return self._build_failure_result(
                explanation="User input is empty.",
                error="User input is empty",
            )

        if self.llm is None:
            logger.error(
                "UNIFIED_EXTRACTION_REJECTED | reason=llm_not_initialized | "
                "initialization_error={}",
                self.initialization_error,
            )
            return self._build_failure_result(
                explanation="The configured Ollama model is unavailable.",
                error=self.initialization_error or "LLM not initialized",
            )

        prompt = UNIFIED_EXTRACTION_PROMPT.format(
            user_input=normalized_input,
        )

        started_at = datetime.now()
        counter_started = time.perf_counter()

        logger.info(
            "OLLAMA_CALL_STARTED | model={} | started_at={} | input_length={}",
            self.model_name,
            started_at.isoformat(timespec="milliseconds"),
            len(normalized_input),
        )

        try:
            response = self.llm.invoke(prompt)
            duration_seconds = time.perf_counter() - counter_started

            logger.info(
                "OLLAMA_CALL_COMPLETED | model={} | duration_seconds={:.3f}",
                self.model_name,
                duration_seconds,
            )

            response_text = self._extract_response_text(response.content)

            logger.debug(
                "UNIFIED_EXTRACTION_RAW_RESPONSE | response={}",
                response_text,
            )

            raw_result = self._extract_json_object(response_text)

            prepared_result = self._prepare_result(
                raw_result=raw_result,
                user_input=normalized_input,
            )

            validated_result = UnifiedExtractionResult.model_validate(
                prepared_result
            )

            final_result = self._derive_username_from_email(
                validated_result
            )

            logger.info(
                "UNIFIED_EXTRACTION_COMPLETED | intent={} | confidence={} | "
                "execution_backend={} | ollama_duration_seconds={:.3f} | "
                "metadata_fields={}",
                final_result.intent.value,
                final_result.confidence,
                (
                    final_result.metadata.execution_backend.value
                    if final_result.metadata.execution_backend is not None
                    else None
                ),
                duration_seconds,
                sorted(
                    final_result.metadata.model_dump(
                        mode="json",
                        exclude_none=True,
                    ).keys()
                ),
            )

            return final_result

        except ValidationError as exc:
            duration_seconds = time.perf_counter() - counter_started
            logger.exception(
                "UNIFIED_EXTRACTION_SCHEMA_INVALID | model={} | "
                "duration_seconds={:.3f} | error_count={}",
                self.model_name,
                duration_seconds,
                exc.error_count(),
            )
            return self._build_failure_result(
                explanation=(
                    "The model response did not match the required "
                    "extraction schema."
                ),
                error="Pydantic validation failed",
            )

        except (ValueError, json.JSONDecodeError) as exc:
            duration_seconds = time.perf_counter() - counter_started
            logger.exception(
                "UNIFIED_EXTRACTION_RESPONSE_INVALID | model={} | "
                "duration_seconds={:.3f} | error_type={}",
                self.model_name,
                duration_seconds,
                type(exc).__name__,
            )
            return self._build_failure_result(
                explanation="The model response could not be parsed safely.",
                error=type(exc).__name__,
            )

        except Exception as exc:
            duration_seconds = time.perf_counter() - counter_started
            logger.exception(
                "OLLAMA_CALL_FAILED | model={} | ollama_host={} | "
                "duration_seconds={:.3f} | error_type={}",
                self.model_name,
                self.ollama_host,
                duration_seconds,
                type(exc).__name__,
            )
            return self._build_failure_result(
                explanation="Intent and metadata extraction failed.",
                error=type(exc).__name__,
            )

    @staticmethod
    def _normalize_user_input(user_input: Any) -> str:
        if not isinstance(user_input, str):
            return ""
        return user_input.strip()

    @classmethod
    def _detect_explicit_execution_backend(
        cls,
        user_input: str,
    ) -> ExecutionBackend | None:
        """
        Detect an explicitly requested backend from the original query.

        If both API and script wording are present, return None so the
        Identity Agent asks for clarification.
        """

        if not isinstance(user_input, str):
            return None

        normalized_input = " ".join(
            user_input.strip().casefold().split()
        )

        script_requested = any(
            re.search(pattern, normalized_input, flags=re.IGNORECASE)
            is not None
            for pattern in cls.SCRIPT_BACKEND_PATTERNS
        )

        api_requested = any(
            re.search(pattern, normalized_input, flags=re.IGNORECASE)
            is not None
            for pattern in cls.API_BACKEND_PATTERNS
        )

        if script_requested and api_requested:
            logger.warning(
                "EXECUTION_BACKEND_AMBIGUOUS | "
                "reason=api_and_script_both_requested"
            )
            return None

        if script_requested:
            return ExecutionBackend.SCRIPT

        if api_requested:
            return ExecutionBackend.API

        return None

    @staticmethod
    def _normalize_llm_backend(
        value: Any,
    ) -> ExecutionBackend | None:
        if isinstance(value, ExecutionBackend):
            return value

        if not isinstance(value, str):
            return None

        normalized_value = value.strip().casefold()

        aliases = {
            "api": ExecutionBackend.API,
            "graph": ExecutionBackend.API,
            "microsoft graph": ExecutionBackend.API,
            "microsoft graph api": ExecutionBackend.API,
            "script": ExecutionBackend.SCRIPT,
            "scripts": ExecutionBackend.SCRIPT,
            "powershell": ExecutionBackend.SCRIPT,
            "powershell script": ExecutionBackend.SCRIPT,
        }

        return aliases.get(normalized_value)

    @staticmethod
    def _extract_response_text(content: Any) -> str:
        if isinstance(content, str):
            normalized_content = content.strip()
            if normalized_content:
                return normalized_content

        if isinstance(content, list):
            text_parts: list[str] = []

            for item in content:
                if isinstance(item, str):
                    text_parts.append(item)
                elif isinstance(item, dict):
                    text_value = item.get("text")
                    if isinstance(text_value, str):
                        text_parts.append(text_value)

            normalized_content = "".join(text_parts).strip()
            if normalized_content:
                return normalized_content

        raise ValueError(
            "The model returned empty or unsupported response content."
        )

    @staticmethod
    def _remove_markdown_fences(response_text: str) -> str:
        cleaned_response = response_text.strip()
        cleaned_response = re.sub(
            r"^```(?:json)?\s*",
            "",
            cleaned_response,
            flags=re.IGNORECASE,
        )
        cleaned_response = re.sub(
            r"\s*```$",
            "",
            cleaned_response,
        )
        return cleaned_response.strip()

    @classmethod
    def _extract_json_object(
        cls,
        response_text: str,
    ) -> dict[str, Any]:
        if not response_text.strip():
            raise ValueError("The model returned an empty response.")

        cleaned_response = cls._remove_markdown_fences(response_text)

        try:
            parsed_response = json.loads(cleaned_response)

            if not isinstance(parsed_response, dict):
                raise ValueError(
                    "The model response was JSON but was not an object."
                )

            if "intent" not in parsed_response:
                raise ValueError(
                    "The model response did not contain an intent field."
                )

            return parsed_response

        except json.JSONDecodeError:
            pass

        decoder = json.JSONDecoder()

        for character_index, character in enumerate(cleaned_response):
            if character != "{":
                continue

            try:
                candidate, _ = decoder.raw_decode(
                    cleaned_response[character_index:]
                )
            except json.JSONDecodeError:
                continue

            if isinstance(candidate, dict) and "intent" in candidate:
                return candidate

        raise ValueError(
            "No valid intent JSON object was found in the model response."
        )

    @classmethod
    def _prepare_result(
        cls,
        *,
        raw_result: dict[str, Any],
        user_input: str,
    ) -> dict[str, Any]:
        """Normalize the model response before Pydantic validation."""

        raw_metadata = raw_result.get("metadata")
        if not isinstance(raw_metadata, dict):
            raw_metadata = {}

        normalized_metadata = {
            field_name: cls._normalize_optional_string(
                raw_metadata.get(field_name)
            )
            for field_name in cls.STRING_METADATA_FIELDS
        }

        normalized_metadata["cpu_count"] = cls._normalize_integer(
            raw_metadata.get("cpu_count")
        )
        normalized_metadata["ram_gb"] = cls._normalize_integer(
            raw_metadata.get("ram_gb")
        )

        explicit_backend = cls._detect_explicit_execution_backend(
            user_input
        )
        llm_backend = cls._normalize_llm_backend(
            raw_metadata.get("execution_backend")
        )

        selected_backend = (
            explicit_backend
            if explicit_backend is not None
            else llm_backend
        )

        normalized_metadata["execution_backend"] = (
            selected_backend.value
            if selected_backend is not None
            else None
        )

        normalized_metadata["approval_granted"] = False
        normalized_metadata["initial_password"] = None
        normalized_metadata["domain_password"] = None
        normalized_metadata["admin_password"] = None

        intent_value = cls._normalize_intent(
            raw_result.get("intent")
        )

        confidence = cls._normalize_confidence(
            raw_result.get("confidence")
        )

        explanation = raw_result.get("explanation")
        if not isinstance(explanation, str) or not explanation.strip():
            explanation = "No explanation was supplied by the model."

        logger.info(
            "EXECUTION_BACKEND_RESOLVED | explicit_backend={} | "
            "llm_backend={} | selected_backend={}",
            explicit_backend.value if explicit_backend else None,
            llm_backend.value if llm_backend else None,
            selected_backend.value if selected_backend else None,
        )

        return {
            "success": True,
            "intent": intent_value,
            "confidence": confidence,
            "explanation": explanation.strip(),
            "metadata": normalized_metadata,
            "error": None,
        }

    @staticmethod
    def _normalize_optional_string(value: Any) -> str | None:
        if value is None:
            return None

        normalized_value = str(value).strip()

        if normalized_value.casefold() in {
            "",
            "null",
            "none",
            "n/a",
            "na",
            "not provided",
            "not available",
        }:
            return None

        return normalized_value

    @staticmethod
    def _normalize_integer(value: Any) -> int | None:
        if value is None:
            return None

        if isinstance(value, str) and not value.strip():
            return None

        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _normalize_intent(value: Any) -> str:
        if not isinstance(value, str):
            return IntentType.UNKNOWN.value

        normalized_value = value.strip().casefold()
        supported_intents = {intent.value for intent in IntentType}

        if normalized_value not in supported_intents:
            logger.warning(
                "UNIFIED_EXTRACTION_UNKNOWN_INTENT | model_intent={}",
                normalized_value,
            )
            return IntentType.UNKNOWN.value

        return normalized_value

    @staticmethod
    def _normalize_confidence(value: Any) -> float:
        try:
            normalized_confidence = float(value)
        except (TypeError, ValueError):
            return 0.0

        return max(0.0, min(1.0, normalized_confidence))

    @staticmethod
    def _derive_username_from_email(
        result: UnifiedExtractionResult,
    ) -> UnifiedExtractionResult:
        metadata = result.metadata

        if metadata.username:
            normalized_metadata = metadata.model_copy(
                update={
                    "username_source": (
                        metadata.username_source or "explicit"
                    )
                }
            )
            return result.model_copy(
                update={"metadata": normalized_metadata}
            )

        if not metadata.email or "@" not in metadata.email:
            return result

        email_local_part = metadata.email.split("@", maxsplit=1)[0].strip()
        if not email_local_part:
            return result

        normalized_metadata = metadata.model_copy(
            update={
                "username": email_local_part,
                "username_source": "derived_from_email",
            }
        )

        logger.info(
            "UNIFIED_EXTRACTION_DERIVED_FIELD | field=username | "
            "source=email | username={}",
            email_local_part,
        )

        return result.model_copy(
            update={"metadata": normalized_metadata}
        )

    @staticmethod
    def _build_failure_result(
        *,
        explanation: str,
        error: str,
    ) -> UnifiedExtractionResult:
        return UnifiedExtractionResult(
            success=False,
            intent=IntentType.UNKNOWN,
            confidence=0.0,
            explanation=explanation,
            metadata=IdentityMetadata(),
            error=error,
        )

    def validate_metadata(
        self,
        metadata: dict[str, Any] | IdentityMetadata,
        intent: str,
    ) -> tuple[bool, str]:
        """Backward-compatible extraction-level validation."""

        try:
            validated_metadata = (
                metadata
                if isinstance(metadata, IdentityMetadata)
                else IdentityMetadata.model_validate(metadata)
            )
        except ValidationError:
            logger.exception(
                "EXTRACTION_METADATA_VALIDATION_FAILED | intent={}",
                intent,
            )
            return False, "Extracted metadata is invalid."

        if intent == IntentType.UNKNOWN.value:
            return False, "The intent is unsupported."

        if (
            intent == IntentType.GET_USER_DETAILS.value
            and not (
                validated_metadata.username
                or validated_metadata.email
                or validated_metadata.user_id
            )
        ):
            return False, "Username, email, or user ID is required."

        return (
            True,
            "Final operation readiness validation will be performed by "
            "IdentityAgent.",
        )

    def get_supported_intents(self) -> list[str]:
        return [
            intent.value
            for intent in IntentType
            if intent is not IntentType.UNKNOWN
        ]
