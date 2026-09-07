"""
Unified Intent and Metadata Extractor Module

Purpose:
    Extract intent and metadata in one timed Ollama invocation.
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

from App.intent.prompts import (
    UNIFIED_EXTRACTION_PROMPT,
)
from App.workflow.state import (
    IdentityMetadata,
    IntentType,
    UnifiedExtractionResult,
)


class UnifiedIntentMetadataExtractor:
    """
    Extract intent and operation metadata using one Ollama call.
    """

    STRING_METADATA_FIELDS = (
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

    def __init__(
        self,
        model_name: str | None = None,
        ollama_host: str | None = None,
    ) -> None:
        self.model_name = (
            model_name
            or os.getenv(
                "MODEL_NAME",
                "qwen3:14b",
            )
        )

        self.ollama_host = (
            ollama_host
            or os.getenv(
                "OLLAMA_HOST",
                "http://localhost:11434",
            )
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
                "UnifiedIntentMetadataExtractor "
                "initialized | model={} | "
                "ollama_host={}",
                self.model_name,
                self.ollama_host,
            )

        except Exception as exc:
            self.initialization_error = (
                type(exc).__name__
            )

            logger.error(
                "UNIFIED_EXTRACTOR_INITIALIZATION_FAILED | "
                "model={} | ollama_host={} | "
                "error_type={} | error={}",
                self.model_name,
                self.ollama_host,
                self.initialization_error,
                str(exc),
            )

    def extract_all(
        self,
        user_input: str,
    ) -> UnifiedExtractionResult:
        normalized_input = (
            user_input.strip()
            if isinstance(user_input, str)
            else ""
        )

        if not normalized_input:
            return self._build_failure_result(
                explanation="User input is empty.",
                error="User input is empty",
            )

        if self.llm is None:
            return self._build_failure_result(
                explanation=(
                    "The configured Ollama model "
                    "is unavailable."
                ),
                error=(
                    self.initialization_error
                    or "LLM not initialized"
                ),
            )

        prompt = (
            UNIFIED_EXTRACTION_PROMPT.format(
                user_input=normalized_input,
            )
        )

        started_at = datetime.now()
        counter_started = time.perf_counter()
        duration_seconds = 0.0

        logger.info(
            "OLLAMA_CALL_STARTED | "
            "model={} | started_at={} | "
            "input_length={}",
            self.model_name,
            started_at.isoformat(
                timespec="milliseconds"
            ),
            len(normalized_input),
        )

        try:
            try:
                response = self.llm.invoke(
                    prompt
                )

            finally:
                duration_seconds = (
                    time.perf_counter()
                    - counter_started
                )

                logger.info(
                    "OLLAMA_CALL_COMPLETED | "
                    "model={} | "
                    "duration_seconds={:.3f}",
                    self.model_name,
                    duration_seconds,
                )

            response_text = (
                self._extract_response_text(
                    response.content
                )
            )

            raw_result = (
                self._extract_json_object(
                    response_text
                )
            )

            prepared_result = (
                self._prepare_result(
                    raw_result
                )
            )

            validated_result = (
                UnifiedExtractionResult
                .model_validate(
                    prepared_result
                )
            )

            final_result = (
                self._derive_username_from_email(
                    validated_result
                )
            )

            logger.info(
                "UNIFIED_EXTRACTION_COMPLETED | "
                "intent={} | confidence={} | "
                "ollama_duration_seconds={:.3f} | "
                "metadata_fields={}",
                final_result.intent.value,
                final_result.confidence,
                duration_seconds,
                sorted(
                    final_result.metadata
                    .model_dump(
                        exclude_none=True
                    )
                    .keys()
                ),
            )

            return final_result

        except ValidationError as exc:
            logger.error(
                "UNIFIED_EXTRACTION_SCHEMA_INVALID | "
                "model={} | error_count={}",
                self.model_name,
                exc.error_count(),
            )

            return self._build_failure_result(
                explanation=(
                    "The model response did not match "
                    "the required schema."
                ),
                error="Pydantic validation failed",
            )

        except (
            ValueError,
            json.JSONDecodeError,
        ) as exc:
            logger.error(
                "UNIFIED_EXTRACTION_RESPONSE_INVALID | "
                "model={} | error_type={} | error={}",
                self.model_name,
                type(exc).__name__,
                str(exc),
            )

            return self._build_failure_result(
                explanation=(
                    "The model response could not be "
                    "parsed or validated."
                ),
                error=type(exc).__name__,
            )

        except Exception as exc:
            logger.error(
                "UNIFIED_EXTRACTION_FAILED | "
                "model={} | ollama_host={} | "
                "error_type={} | error={}",
                self.model_name,
                self.ollama_host,
                type(exc).__name__,
                str(exc),
            )

            return self._build_failure_result(
                explanation=(
                    "Intent and metadata extraction "
                    "failed."
                ),
                error=type(exc).__name__,
            )

    @staticmethod
    def _extract_response_text(
        content: Any,
    ) -> str:
        if isinstance(content, str):
            text = content.strip()

            if text:
                return text

        if isinstance(content, list):
            text_parts: list[str] = []

            for item in content:
                if isinstance(item, str):
                    text_parts.append(item)

                elif isinstance(item, dict):
                    text = item.get("text")

                    if isinstance(text, str):
                        text_parts.append(text)

            combined = "".join(
                text_parts
            ).strip()

            if combined:
                return combined

        raise ValueError(
            "The model returned empty or unsupported "
            "response content."
        )

    @staticmethod
    def _remove_markdown_fences(
        response_text: str,
    ) -> str:
        cleaned = response_text.strip()

        cleaned = re.sub(
            r"^```(?:json)?\s*",
            "",
            cleaned,
            flags=re.IGNORECASE,
        )

        cleaned = re.sub(
            r"\s*```$",
            "",
            cleaned,
        )

        return cleaned.strip()

    @classmethod
    def _extract_json_object(
        cls,
        response_text: str,
    ) -> dict[str, Any]:
        cleaned = (
            cls._remove_markdown_fences(
                response_text
            )
        )

        try:
            parsed = json.loads(cleaned)

            if (
                isinstance(parsed, dict)
                and "intent" in parsed
            ):
                return parsed

        except json.JSONDecodeError:
            pass

        decoder = json.JSONDecoder()

        for index, character in enumerate(
            cleaned
        ):
            if character != "{":
                continue

            try:
                candidate, _ = (
                    decoder.raw_decode(
                        cleaned[index:]
                    )
                )

            except json.JSONDecodeError:
                continue

            if (
                isinstance(candidate, dict)
                and "intent" in candidate
            ):
                return candidate

        raise ValueError(
            "No valid intent JSON object was found."
        )

    @classmethod
    def _prepare_result(
        cls,
        raw_result: dict[str, Any],
    ) -> dict[str, Any]:
        raw_metadata = raw_result.get(
            "metadata"
        )

        if not isinstance(
            raw_metadata,
            dict,
        ):
            raw_metadata = {}

        normalized_metadata = {
            field_name:
                cls._normalize_optional_string(
                    raw_metadata.get(
                        field_name
                    )
                )
            for field_name
            in cls.STRING_METADATA_FIELDS
        }

        normalized_metadata["cpu_count"] = (
            cls._normalize_integer(
                raw_metadata.get(
                    "cpu_count"
                )
            )
        )

        normalized_metadata["ram_gb"] = (
            cls._normalize_integer(
                raw_metadata.get(
                    "ram_gb"
                )
            )
        )

        # The LLM is never trusted to supply approval.
        normalized_metadata[
            "approval_granted"
        ] = False

        # Passwords must come from secure UI fields.
        normalized_metadata[
            "initial_password"
        ] = None

        normalized_metadata[
            "domain_password"
        ] = None

        normalized_metadata[
            "admin_password"
        ] = None

        intent_value = str(
            raw_result.get(
                "intent",
                IntentType.UNKNOWN.value,
            )
        ).strip().casefold()

        supported_intents = {
            intent.value
            for intent in IntentType
        }

        if intent_value not in supported_intents:
            intent_value = (
                IntentType.UNKNOWN.value
            )

        try:
            confidence = float(
                raw_result.get(
                    "confidence",
                    0.0,
                )
            )

        except (
            TypeError,
            ValueError,
        ):
            confidence = 0.0

        confidence = max(
            0.0,
            min(
                1.0,
                confidence,
            ),
        )

        explanation = raw_result.get(
            "explanation"
        )

        if (
            not isinstance(
                explanation,
                str,
            )
            or not explanation.strip()
        ):
            explanation = (
                "No explanation was supplied."
            )

        return {
            "success": True,
            "intent": intent_value,
            "confidence": confidence,
            "explanation":
                explanation.strip(),
            "metadata":
                normalized_metadata,
            "error": None,
        }

    @staticmethod
    def _normalize_optional_string(
        value: Any,
    ) -> str | None:
        if value is None:
            return None

        normalized = str(
            value
        ).strip()

        if normalized.casefold() in {
            "",
            "null",
            "none",
            "n/a",
            "not provided",
            "not available",
        }:
            return None

        return normalized

    @staticmethod
    def _normalize_integer(
        value: Any,
    ) -> int | None:
        if value is None or value == "":
            return None

        try:
            return int(value)

        except (
            TypeError,
            ValueError,
        ):
            return None

    @staticmethod
    def _derive_username_from_email(
        result: UnifiedExtractionResult,
    ) -> UnifiedExtractionResult:
        metadata = result.metadata

        if metadata.username:
            updated_metadata = (
                metadata.model_copy(
                    update={
                        "username_source": (
                            metadata.username_source
                            or "explicit"
                        )
                    }
                )
            )

            return result.model_copy(
                update={
                    "metadata":
                        updated_metadata
                }
            )

        if (
            not metadata.email
            or "@" not in metadata.email
        ):
            return result

        local_part = metadata.email.split(
            "@",
            maxsplit=1,
        )[0].strip()

        if not local_part:
            return result

        updated_metadata = (
            metadata.model_copy(
                update={
                    "username": local_part,
                    "username_source":
                        "derived_from_email",
                }
            )
        )

        return result.model_copy(
            update={
                "metadata":
                    updated_metadata
            }
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
        metadata: (
            dict[str, Any]
            | IdentityMetadata
        ),
        intent: str,
    ) -> tuple[bool, str]:
        try:
            validated_metadata = (
                metadata
                if isinstance(
                    metadata,
                    IdentityMetadata,
                )
                else IdentityMetadata
                .model_validate(metadata)
            )

        except ValidationError:
            return (
                False,
                "Extracted metadata is invalid.",
            )

        if intent == IntentType.UNKNOWN.value:
            return (
                False,
                "The intent is unsupported.",
            )

        if (
            intent
            == IntentType.GET_USER_DETAILS.value
            and not (
                validated_metadata.username
                or validated_metadata.email
                or validated_metadata.user_id
            )
        ):
            return (
                False,
                "Username, email or user ID "
                "is required.",
            )

        return (
            True,
            "Final validation will be performed "
            "by IdentityAgent.",
        )

    def get_supported_intents(
        self,
    ) -> list:
        return [
            intent.value
            for intent in IntentType
            if intent is not IntentType.UNKNOWN
        ]