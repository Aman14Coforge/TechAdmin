"""
Unified Intent and Metadata Extractor Module

Purpose:
    Extract intent and metadata in a single Ollama LLM call.

Responsibilities:
    - Classify the user request into one supported intent.
    - Extract identity and operation metadata.
    - Parse clean, fenced, or reasoning-wrapped JSON.
    - Validate the complete LLM response through Pydantic.
    - Derive username from an explicitly supplied email address when
      username is missing.
    - Return a controlled result when extraction fails.

Does not handle:
    - Agent routing.
    - Mandatory metadata validation for a specific tool.
    - Tool selection.
    - Tool execution.
    - Microsoft Graph API calls.

Final operation-readiness validation belongs to IdentityAgent because
different Identity tools require different metadata.
"""

from __future__ import annotations

import json
import os
import re
from typing import Any, Dict, Optional

from langchain_ollama import ChatOllama
from loguru import logger
from pydantic import ValidationError

from App.intent.prompts import UNIFIED_EXTRACTION_PROMPT
from App.workflow.state import (
    IdentityMetadata,
    IntentType,
    UnifiedExtractionResult,
)


class UnifiedIntentMetadataExtractor:
    """
    Extract intent and metadata using one Ollama LLM invocation.

    This class uses the controlled prompt from App.intent.prompts and
    validates the final result through UnifiedExtractionResult.
    """

    def __init__(
        self,
        model_name: Optional[str] = None,
        ollama_host: Optional[str] = None,
    ) -> None:
        """
        Initialize the unified extractor.

        Args:
            model_name:
                Ollama model name. Uses MODEL_NAME from the environment
                when not explicitly supplied.

            ollama_host:
                Ollama service URL. Uses OLLAMA_HOST from the environment
                when not explicitly supplied.
        """

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

        self.llm: Optional[ChatOllama] = None
        self.initialization_error: Optional[str] = None

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
            self.initialization_error = (
                type(exc).__name__
            )

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
        """
        Extract intent and metadata using one Ollama call.

        Args:
            user_input:
                Natural-language IT operation request.

        Returns:
            Pydantic UnifiedExtractionResult containing:

            - success
            - intent
            - confidence
            - explanation
            - metadata
            - error
        """

        normalized_input = self._normalize_user_input(
            user_input
        )

        if not normalized_input:
            logger.warning(
                "UNIFIED_EXTRACTION_REJECTED | "
                "reason=empty_user_input"
            )

            return self._build_failure_result(
                explanation="User input is empty.",
                error="User input is empty",
            )

        if self.llm is None:
            logger.error(
                "UNIFIED_EXTRACTION_REJECTED | "
                "reason=llm_not_initialized | "
                "initialization_error={}",
                self.initialization_error,
            )

            return self._build_failure_result(
                explanation=(
                    "The Ollama model is unavailable."
                ),
                error=(
                    self.initialization_error
                    or "LLM not initialized"
                ),
            )

        prompt = UNIFIED_EXTRACTION_PROMPT.format(
            user_input=normalized_input,
        )

        logger.info(
            "UNIFIED_EXTRACTION_STARTED | "
            "model={} | input_length={}",
            self.model_name,
            len(normalized_input),
        )

        try:
            response = self.llm.invoke(
                prompt
            )

            response_text = (
                self._extract_response_text(
                    response.content
                )
            )

            logger.debug(
                "UNIFIED_EXTRACTION_RAW_RESPONSE | "
                "response={}",
                response_text,
            )

            raw_result = self._extract_json_object(
                response_text
            )

            prepared_result = self._prepare_result(
                raw_result
            )

            validated_result = (
                UnifiedExtractionResult.model_validate(
                    prepared_result
                )
            )

            final_result = (
                self._normalize_username_from_email(
                    validated_result
                )
            )

            logger.info(
                "UNIFIED_EXTRACTION_COMPLETED | "
                "success={} | intent={} | confidence={} | "
                "username={} | username_source={} | "
                "email={} | user_id={} | "
                "employee_number={} | group_name={} | "
                "time_window={}",
                final_result.success,
                final_result.intent.value,
                final_result.confidence,
                final_result.metadata.username,
                final_result.metadata.username_source,
                final_result.metadata.email,
                final_result.metadata.user_id,
                final_result.metadata.employee_number,
                final_result.metadata.group_name,
                final_result.metadata.time_window,
            )

            return final_result

        except ValidationError as exc:
            logger.exception(
                "UNIFIED_EXTRACTION_SCHEMA_VALIDATION_FAILED | "
                "model={} | error_count={}",
                self.model_name,
                exc.error_count(),
            )

            return self._build_failure_result(
                explanation=(
                    "The model response did not match the "
                    "required extraction schema."
                ),
                error="Pydantic validation failed",
            )

        except json.JSONDecodeError:
            logger.exception(
                "UNIFIED_EXTRACTION_JSON_PARSING_FAILED | "
                "model={}",
                self.model_name,
            )

            return self._build_failure_result(
                explanation=(
                    "The model did not return valid JSON."
                ),
                error="JSON parsing failed",
            )

        except ValueError as exc:
            logger.exception(
                "UNIFIED_EXTRACTION_RESPONSE_INVALID | "
                "model={} | error_type={}",
                self.model_name,
                type(exc).__name__,
            )

            return self._build_failure_result(
                explanation=(
                    "The model response could not be "
                    "interpreted safely."
                ),
                error=str(exc),
            )

        except Exception as exc:
            logger.exception(
                "UNIFIED_EXTRACTION_FAILED | "
                "model={} | error_type={}",
                self.model_name,
                type(exc).__name__,
            )

            return self._build_failure_result(
                explanation=(
                    "Intent and metadata extraction failed."
                ),
                error=type(exc).__name__,
            )

    @staticmethod
    def _normalize_user_input(
        user_input: Any,
    ) -> str:
        """
        Normalize incoming user input without changing its meaning.
        """

        if not isinstance(
            user_input,
            str,
        ):
            return ""

        return user_input.strip()

    @staticmethod
    def _extract_response_text(
        content: Any,
    ) -> str:
        """
        Convert ChatOllama response content into plain text.

        Chat model integrations can return either a string or a list of
        content blocks.
        """

        if isinstance(
            content,
            str,
        ):
            normalized_content = content.strip()

            if normalized_content:
                return normalized_content

        if isinstance(
            content,
            list,
        ):
            text_parts: list[str] = []

            for item in content:
                if isinstance(
                    item,
                    str,
                ):
                    text_parts.append(
                        item
                    )

                elif isinstance(
                    item,
                    dict,
                ):
                    text_value = item.get(
                        "text"
                    )

                    if isinstance(
                        text_value,
                        str,
                    ):
                        text_parts.append(
                            text_value
                        )

            normalized_content = "".join(
                text_parts
            ).strip()

            if normalized_content:
                return normalized_content

        raise ValueError(
            "The model returned an empty or unsupported "
            "response format."
        )

    @classmethod
    def _extract_json_object(
        cls,
        response_text: str,
    ) -> Dict[str, Any]:
        """
        Extract the intended JSON object from the model response.

        Supported response formats:

        1. Pure JSON
        2. JSON inside markdown fences
        3. JSON surrounded by model reasoning
        4. JSON preceded or followed by additional text

        The selected JSON object must contain an intent field.
        """

        if not response_text.strip():
            raise ValueError(
                "The model returned an empty response."
            )

        cleaned_response = cls._remove_markdown_fences(
            response_text
        )

        try:
            parsed_response = json.loads(
                cleaned_response
            )

            if not isinstance(
                parsed_response,
                dict,
            ):
                raise ValueError(
                    "The model response was JSON but was "
                    "not a JSON object."
                )

            if "intent" not in parsed_response:
                raise ValueError(
                    "The model response did not contain "
                    "an intent field."
                )

            return parsed_response

        except json.JSONDecodeError:
            pass

        decoder = json.JSONDecoder()

        valid_candidates: list[
            Dict[str, Any]
        ] = []

        for character_index, character in enumerate(
            cleaned_response
        ):
            if character != "{":
                continue

            try:
                candidate, _ = decoder.raw_decode(
                    cleaned_response[
                        character_index:
                    ]
                )

            except json.JSONDecodeError:
                continue

            if not isinstance(
                candidate,
                dict,
            ):
                continue

            if "intent" not in candidate:
                continue

            valid_candidates.append(
                candidate
            )

        if not valid_candidates:
            raise ValueError(
                "No valid intent JSON object was found "
                "in the model response."
            )

        return valid_candidates[0]

    @staticmethod
    def _remove_markdown_fences(
        response_text: str,
    ) -> str:
        """
        Remove optional JSON markdown fences.
        """

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
    def _prepare_result(
        cls,
        raw_result: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Prepare the raw LLM response for Pydantic validation.

        Unknown intent values are converted to unknown rather than being
        trusted or forwarded directly.
        """

        raw_metadata = raw_result.get(
            "metadata"
        )

        if not isinstance(
            raw_metadata,
            dict,
        ):
            raw_metadata = {}

        normalized_metadata = {
            "username": cls._normalize_optional_string(
                raw_metadata.get(
                    "username"
                )
            ),
            "user_id": cls._normalize_optional_string(
                raw_metadata.get(
                    "user_id"
                )
            ),
            "email": cls._normalize_optional_string(
                raw_metadata.get(
                    "email"
                )
            ),
            "employee_number":
                cls._normalize_optional_string(
                    raw_metadata.get(
                        "employee_number"
                    )
                ),
            "group_name":
                cls._normalize_optional_string(
                    raw_metadata.get(
                        "group_name"
                    )
                ),
            "time_window":
                cls._normalize_optional_string(
                    raw_metadata.get(
                        "time_window"
                    )
                ),
            "username_source":
                cls._normalize_username_source(
                    raw_metadata.get(
                        "username_source"
                    )
                ),
        }

        normalized_intent = cls._normalize_intent(
            raw_result.get(
                "intent"
            )
        )

        normalized_confidence = (
            cls._normalize_confidence(
                raw_result.get(
                    "confidence"
                )
            )
        )

        explanation = raw_result.get(
            "explanation"
        )

        if not isinstance(
            explanation,
            str,
        ) or not explanation.strip():
            explanation = (
                "No intent explanation was supplied "
                "by the model."
            )

        return {
            "success": True,
            "intent": normalized_intent,
            "confidence":
                normalized_confidence,
            "explanation":
                explanation.strip(),
            "metadata":
                normalized_metadata,
            "error":
                None,
        }

    @staticmethod
    def _normalize_optional_string(
        value: Any,
    ) -> Optional[Any]:
        """
        Normalize blank and null-like strings to None.
        """

        if value is None:
            return None

        if not isinstance(
            value,
            str,
        ):
            return str(
                value
            ).strip() or None

        normalized_value = value.strip()

        if normalized_value.casefold() in {
            "",
            "null",
            "none",
            "not provided",
            "not available",
            "n/a",
        }:
            return None

        return normalized_value

    @staticmethod
    def _normalize_username_source(
        value: Any,
    ) -> Optional[Any]:
        """
        Allow only controlled username-source values.
        """

        if not isinstance(
            value,
            str,
        ):
            return None

        normalized_value = (
            value.strip().casefold()
        )

        if normalized_value in {
            "explicit",
            "derived_from_email",
        }:
            return normalized_value

        return None

    @staticmethod
    def _normalize_intent(
        value: Any,
    ) -> str:
        """
        Accept only a controlled IntentType value.
        """

        if not isinstance(
            value,
            str,
        ):
            return IntentType.UNKNOWN.value

        normalized_value = (
            value.strip().casefold()
        )

        supported_intents = {
            intent.value
            for intent in IntentType
        }

        if normalized_value not in supported_intents:
            logger.warning(
                "UNIFIED_EXTRACTION_UNKNOWN_INTENT | "
                "model_intent={}",
                normalized_value,
            )

            return IntentType.UNKNOWN.value

        return normalized_value

    @staticmethod
    def _normalize_confidence(
        value: Any,
    ) -> float:
        """
        Normalize LLM confidence into the range 0.0 to 1.0.
        """

        try:
            normalized_confidence = float(
                value
            )

        except (
            TypeError,
            ValueError,
        ):
            return 0.0

        if normalized_confidence < 0.0:
            return 0.0

        if normalized_confidence > 1.0:
            return 1.0

        return normalized_confidence

    @staticmethod
    def _normalize_username_from_email(
        result: UnifiedExtractionResult,
    ) -> UnifiedExtractionResult:
        """
        Derive username from an explicitly supplied email address when
        the username is missing.

        Example:

            Shreesanyog.Rath@Coforge.com

        becomes:

            username = Shreesanyog.Rath
            username_source = derived_from_email

        This is deterministic normalization and does not require another
        LLM call.
        """

        metadata = result.metadata

        if metadata.username:
            normalized_metadata = metadata.model_copy(
                update={
                    "username_source": (
                        metadata.username_source
                        or "explicit"
                    )
                }
            )

            return result.model_copy(
                update={
                    "metadata":
                        normalized_metadata
                }
            )

        if not metadata.email:
            return result

        if "@" not in metadata.email:
            return result

        email_local_part = metadata.email.split(
            "@",
            maxsplit=1,
        )[0].strip()

        if not email_local_part:
            return result

        normalized_metadata = metadata.model_copy(
            update={
                "username":
                    email_local_part,
                "username_source":
                    "derived_from_email",
            }
        )

        logger.info(
            "UNIFIED_EXTRACTION_DERIVED_FIELD | "
            "field=username | source=email | "
            "username={}",
            email_local_part,
        )

        return result.model_copy(
            update={
                "metadata":
                    normalized_metadata
            }
        )

    @staticmethod
    def _build_failure_result(
        *,
        explanation: str,
        error: str,
    ) -> UnifiedExtractionResult:
        """
        Return a controlled failed extraction result.
        """

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
            Dict[str, Any]
            | IdentityMetadata
        ),
        intent: str,
    ) -> tuple[bool, str]:
        """
        Backward-compatible metadata-validation method.

        Important:
            Final metadata readiness validation belongs to IdentityAgent
            because each tool has different required fields.

        This method performs only basic extraction-level validation for
        existing callers such as the older DemoFlow.
        """

        try:
            validated_metadata = (
                metadata
                if isinstance(
                    metadata,
                    IdentityMetadata,
                )
                else IdentityMetadata.model_validate(
                    metadata
                )
            )

        except ValidationError:
            logger.exception(
                "EXTRACTION_METADATA_VALIDATION_FAILED | "
                "intent={}",
                intent,
            )

            return (
                False,
                (
                    "Extracted metadata does not match "
                    "the required schema."
                ),
            )

        if intent == IntentType.UNKNOWN.value:
            return (
                False,
                (
                    "The request does not match a "
                    "supported intent."
                ),
            )

        if intent == IntentType.GET_USER_DETAILS.value:
            if not (
                validated_metadata.username
                or validated_metadata.email
                or validated_metadata.user_id
            ):
                return (
                    False,
                    (
                        "Username, email address, or "
                        "user ID is required to retrieve "
                        "user details."
                    ),
                )

        return (
            True,
            (
                "Metadata extraction completed. "
                "Final readiness validation will be "
                "performed by the selected agent."
            ),
        )

    def get_supported_intents(
        self,
    ) -> list:
        """
        Return all controlled intents.
        """

        return [
            intent.value
            for intent in IntentType
            if intent is not IntentType.UNKNOWN
        ]