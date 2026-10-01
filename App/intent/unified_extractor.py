"""Semantic unified intent and metadata extractor for TechAdmin."""
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
from App.workflow.state import ExecutionBackend, IdentityMetadata, IntentType, UnifiedExtractionResult


class UnifiedIntentMetadataExtractor:
    """Use Llama 3.2 for semantic extraction, then enforce trusted policies."""

    EMAIL_PATTERN = re.compile(
        r"(?<![\w.+-])(?P<email>[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,})(?![\w.-])",
        re.IGNORECASE,
    )
    BACKEND_SCRIPT_PATTERN = re.compile(
        r"\b(?:via|using|through|with)\s+(?:a\s+|the\s+)?(?:powershell|script|scripts|ad script)\b|\bpowershell\b",
        re.IGNORECASE,
    )
    BACKEND_API_PATTERN = re.compile(
        r"\b(?:via|using|through|with|on)\s+(?:an?\s+|the\s+)?(?:api|entra|microsoft entra|microsoft graph|graph api)\b|\b(?:microsoft\s+entra|microsoft\s+graph)\b",
        re.IGNORECASE,
    )

    STRING_FIELDS = (
        "username", "user_id", "email", "employee_number", "username_source",
        "group_name", "time_window", "first_name", "last_name", "department",
        "target_ou", "description", "target_host", "vm_name", "vswitch_name",
        "ip_address", "subnet", "gateway", "dns", "hostname", "domain", "domain_user",
    )

    DEFAULT_BACKEND_BY_INTENT = {
        IntentType.GET_USER_DETAILS: ExecutionBackend.SCRIPT,
        IntentType.GET_COMPUTER_DETAILS: ExecutionBackend.SCRIPT,
        IntentType.PASSWORD_RESET: ExecutionBackend.API,
    }

    def __init__(self, model_name: str | None = None, ollama_host: str | None = None) -> None:
        self.model_name = model_name or os.getenv("MODEL_NAME", "llama3.2:latest")
        self.ollama_host = ollama_host or os.getenv("OLLAMA_HOST", "http://localhost:11434")
        self.llm: ChatOllama | None = None
        self.initialization_error: str | None = None
        try:
            self.llm = ChatOllama(model=self.model_name, base_url=self.ollama_host, temperature=0, format="json")
            logger.info("Unified extractor initialized | model={} | host={}", self.model_name, self.ollama_host)
        except Exception as exc:
            self.initialization_error = type(exc).__name__
            logger.exception("Unified extractor initialization failed | model={} | type={}", self.model_name, self.initialization_error)

    def extract_all(self, user_input: str) -> UnifiedExtractionResult:
        normalized = user_input.strip() if isinstance(user_input, str) else ""
        if not normalized:
            return self._failure("User input is empty.", "User input is empty")
        if self.llm is None:
            return self._failure("The configured Ollama model is unavailable.", self.initialization_error or "LLM not initialized")

        prompt = UNIFIED_EXTRACTION_PROMPT.format(user_input=normalized)
        started = datetime.now()
        timer = time.perf_counter()
        logger.info("OLLAMA_CALL_STARTED | model={} | started_at={} | length={}", self.model_name, started.isoformat(timespec="milliseconds"), len(normalized))
        try:
            response = self.llm.invoke(prompt)
            elapsed = time.perf_counter() - timer
            raw = self._json_object(self._response_text(response.content))
            result = UnifiedExtractionResult.model_validate(self._prepare(raw, normalized))
            logger.info(
                "UNIFIED_EXTRACTION_COMPLETED | intent={} | backend={} | confidence={} | seconds={:.3f}",
                result.intent.value,
                result.metadata.execution_backend.value if result.metadata.execution_backend else None,
                result.confidence,
                elapsed,
            )
            return result
        except ValidationError as exc:
            logger.exception("Unified extraction schema validation failed | count={}", exc.error_count())
            return self._failure("The model response did not match the extraction schema.", "Pydantic validation failed")
        except Exception as exc:
            logger.exception("Unified extraction failed | type={} | seconds={:.3f}", type(exc).__name__, time.perf_counter() - timer)
            return self._failure("Intent and metadata extraction failed.", type(exc).__name__)

    def _prepare(self, raw_result: dict[str, Any], user_input: str) -> dict[str, Any]:
        raw_metadata = raw_result.get("metadata")
        if not isinstance(raw_metadata, dict):
            raw_metadata = {}
        metadata: dict[str, Any] = {field: self._optional_string(raw_metadata.get(field)) for field in self.STRING_FIELDS}
        metadata["cpu_count"] = self._integer(raw_metadata.get("cpu_count"))
        metadata["ram_gb"] = self._integer(raw_metadata.get("ram_gb"))

        intent = self._intent(raw_result.get("intent"))
        confidence = self._confidence(raw_result.get("confidence"))
        explanation = self._optional_string(raw_result.get("explanation")) or f"The request was classified as {intent.value}."

        explicit_email = self.EMAIL_PATTERN.search(user_input)
        if explicit_email:
            email = explicit_email.group("email")
            metadata["email"] = email
            metadata["username"] = email.split("@", 1)[0]
            metadata["username_source"] = "derived_from_email"

        explicit_backend = self._explicit_backend(user_input)
        if intent is IntentType.GET_COMPUTER_DETAILS:
            selected_backend = ExecutionBackend.SCRIPT
        else:
            selected_backend = explicit_backend or self.DEFAULT_BACKEND_BY_INTENT.get(intent)
        metadata["execution_backend"] = selected_backend.value if selected_backend else None

        metadata["approval_granted"] = False
        metadata["initial_password"] = None
        metadata["domain_password"] = None
        metadata["admin_password"] = None

        return {
            "success": True,
            "intent": intent.value,
            "confidence": confidence,
            "explanation": explanation,
            "metadata": metadata,
            "error": None,
        }

    @classmethod
    def _explicit_backend(cls, text: str) -> ExecutionBackend | None:
        script = cls.BACKEND_SCRIPT_PATTERN.search(text) is not None
        api = cls.BACKEND_API_PATTERN.search(text) is not None
        if script and api:
            logger.warning("Both API and script backends were explicitly requested")
            return None
        if script:
            return ExecutionBackend.SCRIPT
        if api:
            return ExecutionBackend.API
        return None

    @staticmethod
    def _intent(value: Any) -> IntentType:
        if not isinstance(value, str):
            return IntentType.UNKNOWN
        try:
            return IntentType(value.strip().casefold())
        except ValueError:
            return IntentType.UNKNOWN

    @staticmethod
    def _optional_string(value: Any) -> str | None:
        if value is None:
            return None
        normalized = str(value).strip()
        return None if normalized.casefold() in {"", "null", "none", "n/a", "na", "not provided", "not available"} else normalized

    @staticmethod
    def _integer(value: Any) -> int | None:
        if value is None or (isinstance(value, str) and not value.strip()):
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _confidence(value: Any) -> float:
        try:
            return max(0.0, min(1.0, float(value)))
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _response_text(content: Any) -> str:
        if isinstance(content, str) and content.strip():
            return content.strip()
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, str):
                    parts.append(item)
                elif isinstance(item, dict) and isinstance(item.get("text"), str):
                    parts.append(item["text"])
            combined = "".join(parts).strip()
            if combined:
                return combined
        raise ValueError("The model returned empty or unsupported content.")

    @staticmethod
    def _json_object(response_text: str) -> dict[str, Any]:
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", response_text.strip(), flags=re.IGNORECASE)
        try:
            parsed = json.loads(cleaned)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass
        decoder = json.JSONDecoder()
        for index, character in enumerate(cleaned):
            if character != "{":
                continue
            try:
                candidate, _ = decoder.raw_decode(cleaned[index:])
            except json.JSONDecodeError:
                continue
            if isinstance(candidate, dict) and "intent" in candidate:
                return candidate
        raise ValueError("No valid extraction JSON object was found.")

    @staticmethod
    def _failure(explanation: str, error: str) -> UnifiedExtractionResult:
        return UnifiedExtractionResult(success=False, intent=IntentType.UNKNOWN, confidence=0.0, explanation=explanation, metadata=IdentityMetadata(), error=error)

    def validate_metadata(self, metadata: dict[str, Any] | IdentityMetadata, intent: str) -> tuple[bool, str]:
        try:
            validated = metadata if isinstance(metadata, IdentityMetadata) else IdentityMetadata.model_validate(metadata)
        except ValidationError:
            return False, "Extracted metadata is invalid."

        if intent == IntentType.UNKNOWN.value:
            return False, "The request could not be mapped to a supported operation."

        single_user_intents = {
            IntentType.GET_USER_DETAILS.value,
            IntentType.PASSWORD_RESET.value,
            IntentType.ACCOUNT_UNLOCK.value,
            IntentType.FAILED_LOGIN_INVESTIGATION.value,
            IntentType.GRANT_ACCESS.value,
            IntentType.REVOKE_ACCESS.value,
        }
        if intent in single_user_intents and not (validated.username or validated.email or validated.user_id or validated.employee_number):
            return False, "A username, email, user ID, or employee number is required."

        if intent == IntentType.GET_COMPUTER_DETAILS.value and not validated.hostname:
            return False, "A computer name or hostname is required."

        if intent in {IntentType.GRANT_ACCESS.value, IntentType.REVOKE_ACCESS.value} and not validated.group_name:
            return False, "A group name is required."

        return True, "Metadata is valid."

    def get_supported_intents(self) -> list[str]:
        return [intent.value for intent in IntentType if intent is not IntentType.UNKNOWN]
