"""
Unified Intent and Metadata Extractor Module

Purpose:
    Extract a supported TechAdmin intent and its metadata in one timed
    Ollama invocation, then apply narrow deterministic safeguards for
    explicit administrative commands.

Responsibilities:
    - Classify one supported TechAdmin intent.
    - Extract identity and infrastructure metadata.
    - Detect an explicitly requested API or script backend.
    - Default password_reset and get_user_details to API when no backend
      is explicitly requested.
    - Correct clear intent mistakes for low-ambiguity command phrases.
    - Parse clean, fenced, or reasoning-wrapped JSON.
    - Validate the normalized result through Pydantic.
    - Derive username from email when username is absent.
    - Recover username and group name from explicit add/remove membership
      commands when the LLM omits or mislabels them.
    - Measure and log Ollama execution time.
    - Return controlled failure results.

Security:
    - The LLM is never trusted to grant approval.
    - Passwords are never accepted from LLM output.
    - API/script backend is selected only from explicit user wording, a
      controlled LLM value, or the documented API default.
    - Deterministic intent detection uses narrow, operation-specific
      patterns and does not execute tools by itself.
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
    """Extract and normalize one TechAdmin intent and its metadata."""

    EXPLICIT_EMAIL_PATTERN = re.compile(
        r"(?<![\w.+-])[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}(?![\w.-])",
        re.IGNORECASE,
    )
    EXPLICIT_DETAILS_USERNAME_PATTERN = re.compile(
        r"\b(?:details?|information?|profile|account)\s+(?:for\s+|of\s+)?"
        r"([A-Z0-9][A-Z0-9._-]{1,})\b",
        re.IGNORECASE,
    )
    EXPLICIT_TARGET_PATTERN = re.compile(
        r"\b(?:for|of)\s+(?:the\s+)?(?:user\s+|account\s+)?"
        r"([A-Z0-9][A-Z0-9._-]{1,}(?:@[A-Z0-9.-]+\.[A-Z]{2,})?)\b",
        re.IGNORECASE,
    )
    EXPLICIT_LOCKOUT_USERNAME_PATTERN = re.compile(
        r"\bwhy\s+is\s+(?:the\s+)?(?:user\s+|account\s+)?"
        r"([A-Z0-9][A-Z0-9._-]{1,})\s+locked\s+out\b",
        re.IGNORECASE,
    )

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

    EXPLICIT_EMAIL_PATTERN = re.compile(
        r"(?P<email>[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,})",
        flags=re.IGNORECASE,
    )

    DETERMINISTIC_INTENT_PATTERNS: dict[IntentType, tuple[str, ...]] = {
        IntentType.GET_USER_DETAILS: (
            r"\bget\s+(?:the\s+)?(?:ad\s+)?user\s+details?\b",
            r"\bget\s+details?\s+(?:for|of)\s+(?:the\s+)?(?:ad\s+)?user\b",
            r"\bshow\s+(?:the\s+)?(?:ad\s+)?user\s+(?:details?|information)\b",
            r"\bshow\s+(?:the\s+)?(?:user\s+)?information\b",
            r"\bfind\s+(?:the\s+)?(?:ad\s+)?user\s+(?:details?|information)\b",
            r"\blook\s*up\s+(?:the\s+)?(?:ad\s+)?user\b",
            r"\bretrieve\s+(?:the\s+)?(?:ad\s+)?user\s+(?:details?|information)\b",
            r"\bshow\s+(?:the\s+)?(?:user\s+)?(?:profile|account)\b",
            r"\bretrieve\s+(?:the\s+)?(?:user\s+)?(?:profile|account)\b",
            r"\blook\s*\s*up\s+(?:the\s+)?(?:user\s+)?(?:profile|account)\b",
            r"\bwhat\s+(?:do\s+we\s+know|is\s+known)\s+about\b",
        ),
        IntentType.PASSWORD_RESET: (
            r"\breset\s+(?:the\s+)?(?:user\s+|account\s+)?password\b",
            r"\bchange\s+(?:the\s+)?(?:user\s+|account\s+)?password\b",
            r"\bpassword\s+reset\b",
            r"\brecover\s+(?:the\s+)?(?:user\s+|account\s+)?password\b",
            r"\bgenerate\s+(?:a\s+)?(?:new\s+)?password\b",
            r"\bissue\s+(?:a\s+)?(?:new\s+)?password\b",
            r"\bpassword\s+reset\s+(?:is\s+)?required\b",
        ),
        IntentType.ACCOUNT_UNLOCK: (
            r"\bunlock\s+(?:the\s+)?(?:ad\s+)?(?:user\s+)?account\b",
            r"\bunlock\s+(?:the\s+)?(?:ad\s+)?user\b",
            r"\baccount\s+unlock\b",
        ),
        IntentType.GRANT_ACCESS: (
            r"\badd\s+(?:existing\s+)?(?:ad\s+)?user\s+.+?\s+to\s+(?:the\s+)?(?:existing\s+)?(?:ad\s+)?group\s+\S+",
            r"\badd\s+\S+\s+to\s+(?:the\s+)?(?:ad\s+)?group\s+\S+",
            r"\badd\s+\S+\s+to\s+\S+\s+group\b",
            r"\bgrant\s+(?:user\s+)?\S+\s+access\s+to\s+(?:group\s+)?\S+",
            r"\bgrant\s+access\s+to\s+\S+\s+(?:in|through|via)\s+(?:group\s+)?\S+",
        ),
        IntentType.GRANT_ACCESS: (
        (
            r"\badd\s+(?:the\s+)?(?:existing\s+)?"
            r"(?:ad\s+)?user\s+.+?\s+to\s+"
            r"(?:the\s+)?(?:existing\s+)?"
            r"(?:ad\s+)?group\s+\S+"
        ),
        (
            r"\badd\s+\S+\s+to\s+"
            r"(?:the\s+)?(?:ad\s+)?group\s+\S+"
        ),
        (
            r"\b(?:put|place|assign)\s+(?:the\s+)?(?:user\s+)?\S+\s+"
            r"(?:in|into|to)\s+(?:the\s+)?(?:group\s+)?\S+(?:\s+group)?"
        ),
        (
            r"\bgrant\s+(?:the\s+)?(?:user\s+)?"
            r"\S+\s+access\s+to\s+"
            r"(?:the\s+)?(?:group\s+)?\S+"
        ),
    ),

    IntentType.REVOKE_ACCESS: (
        (
            r"\bremove\s+(?:the\s+)?(?:existing\s+)?"
            r"(?:ad\s+)?user\s+.+?\s+from\s+"
            r"(?:the\s+)?(?:existing\s+)?"
            r"(?:ad\s+)?group\s+\S+"
        ),
        (
            r"\bremove\s+\S+\s+from\s+"
            r"(?:the\s+)?(?:ad\s+)?group\s+\S+"
        ),
        (
            r"\b(?:take|remove)\s+(?:the\s+)?(?:user\s+)?\S+\s+"
            r"out\s+of\s+(?:the\s+)?(?:group\s+)?\S+(?:\s+group)?"
        ),
        (
            r"\bremove\s+(?:the\s+)?(?:user\s+)?\S+\s+from\s+"
            r"(?:the\s+)?\S+(?:\s+group)?"
        ),
        (
            r"\brevoke\s+(?:the\s+)?(?:user\s+)?"
            r"\S+\s+access\s+(?:to|from)\s+"
            r"(?:the\s+)?(?:group\s+)?\S+"
        ),
    ),
         IntentType.CREATE_GROUP: (
            r"\bcreate\s+(?:a\s+|an\s+)?(?:new\s+)?(?:ad\s+)?(?:security\s+)?group\b",
            r"\bnew\s+(?:ad\s+)?(?:security\s+)?group\b",
            r"\bprovision\s+(?:a\s+|an\s+)?(?:new\s+)?(?:ad\s+)?group\b",
        ),
        IntentType.CREATE_USER: (
            r"\bcreate\s+(?:a\s+|an\s+)?(?:new\s+)?(?:active\s+directory\s+|ad\s+)?user(?:\s+account)?\b",
            r"\bprovision\s+(?:a\s+|an\s+)?(?:new\s+)?(?:active\s+directory\s+|ad\s+)?user\b",
            r"\bonboard\s+(?:a\s+|an\s+)?(?:new\s+)?(?:active\s+directory\s+|ad\s+)?user\b",
        ),
        IntentType.DELETE_USER: (
            r"\bdelete\s+(?:the\s+)?(?:active\s+directory\s+|ad\s+)?user(?:\s+account)?\b",
            r"\bremove\s+(?:the\s+)?(?:active\s+directory\s+|ad\s+)?user\s+account\b",
            r"\bdeprovision\s+(?:the\s+)?(?:active\s+directory\s+|ad\s+)?user\b",
        ),
       IntentType.FAILED_LOGIN_INVESTIGATION: (
    # Failed login and sign-in investigation wording
    (
        r"\binvestigate\s+(?:the\s+)?"
        r"failed\s+(?:logins?|logons?|sign[ -]?ins?)\b"
    ),
    (
        r"\bcheck\s+(?:the\s+)?"
        r"failed\s+(?:logins?|logons?|sign[ -]?ins?)\b"
    ),
    (
        r"\banaly[sz]e\s+(?:the\s+)?"
        r"failed\s+(?:logins?|logons?|sign[ -]?ins?)\b"
    ),

    # Direct account-lockout investigation wording
    (
        r"\binvestigate\s+(?:the\s+)?"
        r"(?:account\s+)?lockouts?\b"
    ),
    (
        r"\bcheck\s+(?:the\s+)?"
        r"(?:account\s+)?lockouts?\b"
    ),
    (
        r"\banaly[sz]e\s+(?:the\s+)?"
        r"(?:account\s+)?lockouts?\b"
    ),
    (
        r"\baccount\s+lockout\s+investigation\b"
    ),
    (
        r"\blockout\s+investigation\b"
    ),

    # Authentication failure wording
    (
        r"\binvestigate\s+(?:the\s+)?"
        r"authentication\s+failures?\b"
    ),
    (
        r"\bcheck\s+(?:the\s+)?"
        r"authentication\s+failures?\b"
    ),
    (
        r"\bauthentication\s+failures?\b"
    ),

    # Natural-language diagnostic wording
    (
        r"\bwhy\s+(?:is|was|does|did)\s+.+?\s+"
        r"(?:locked|lock(?:ing|ed)?\s+out)\b"
    ),
    (
        r"\bwhy\s+(?:is|was)\s+(?:the\s+)?"
        r"account\s+locked\b"
    ),
    (
        r"\bfind\s+(?:the\s+)?cause\s+of\s+"
        r"(?:the\s+)?(?:account\s+)?lockout\b"
    ),
),
        IntentType.CREATE_VM: (
            r"\bcreate\s+(?:a\s+|an\s+)?(?:new\s+)?vm\b",
            r"\bcreate\s+(?:a\s+|an\s+)?(?:new\s+)?virtual\s+machine\b",
            r"\bprovision\s+(?:a\s+|an\s+)?(?:new\s+)?vm\b",
            r"\bprovision\s+(?:a\s+|an\s+)?(?:new\s+)?virtual\s+machine\b",
        ),
    }

    DEFAULT_API_INTENTS: set[IntentType] = {
        IntentType.GET_USER_DETAILS,
        IntentType.PASSWORD_RESET,
    }

    MEMBERSHIP_PATTERN = re.compile(
        r"\b(?P<verb>add|put|place|assign|remove|take)\s+"
        r"(?:the\s+)?"
        r"(?:existing\s+)?"
        r"(?:ad\s+)?"
        r"(?:user\s+)?"
        r"(?P<user>[^\s,]+)\s+"
        r"(?P<direction>to|from|in|into|out\s+of)\s+"
        r"(?:the\s+)?"
        r"(?:existing\s+)?"
        r"(?:ad\s+)?"
        r"(?:group\s+)?"
        r"(?P<group>[^\s,.;]+)(?:\s+group\b)?",
        flags=re.IGNORECASE,
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
                "UnifiedIntentMetadataExtractor initialized | model={} | ollama_host={}",
                self.model_name,
                self.ollama_host,
            )
        except Exception as exc:
            self.initialization_error = type(exc).__name__
            logger.exception(
                "UNIFIED_EXTRACTOR_INITIALIZATION_FAILED | model={} | "
                "ollama_host={} | error_type={}",
                self.model_name,
                self.ollama_host,
                self.initialization_error,
            )

    def extract_all(self, user_input: str) -> UnifiedExtractionResult:
        """Extract and validate intent and metadata from one request."""

        normalized_input = self._normalize_user_input(user_input)
        if not normalized_input:
            return self._build_failure_result(
                explanation="User input is empty.",
                error="User input is empty",
            )

        if self.llm is None:
            return self._build_failure_result(
                explanation="The configured Ollama model is unavailable.",
                error=self.initialization_error or "LLM not initialized",
            )

        prompt = UNIFIED_EXTRACTION_PROMPT.format(user_input=normalized_input)
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
                "UNIFIED_EXTRACTION_RAW_RESPONSE | response_length={}",
                len(response_text),
            )

            raw_result = self._extract_json_object(response_text)
            prepared_result = self._prepare_result(
                raw_result=raw_result,
                user_input=normalized_input,
            )
            validated_result = UnifiedExtractionResult.model_validate(
                prepared_result
            )
            final_result = self._derive_username_from_email(validated_result)

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
                explanation="The model response did not match the required extraction schema.",
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
        return user_input.strip() if isinstance(user_input, str) else ""

    @classmethod
    def _detect_explicit_execution_backend(
        cls,
        user_input: str,
    ) -> ExecutionBackend | None:
        if not isinstance(user_input, str):
            return None

        normalized = " ".join(user_input.strip().casefold().split())
        script_requested = any(
            re.search(pattern, normalized) is not None
            for pattern in cls.SCRIPT_BACKEND_PATTERNS
        )
        api_requested = any(
            re.search(pattern, normalized) is not None
            for pattern in cls.API_BACKEND_PATTERNS
        )

        if script_requested and api_requested:
            logger.warning(
                "EXECUTION_BACKEND_AMBIGUOUS | reason=api_and_script_both_requested"
            )
            return None
        if script_requested:
            return ExecutionBackend.SCRIPT
        if api_requested:
            return ExecutionBackend.API
        return None

    @classmethod
    def _detect_deterministic_intent(
        cls,
        user_input: str,
    ) -> IntentType | None:
        if not isinstance(user_input, str):
            return None

        normalized = " ".join(user_input.strip().casefold().split())
        matched = [
            intent
            for intent, patterns in cls.DETERMINISTIC_INTENT_PATTERNS.items()
            if any(re.search(pattern, normalized) is not None for pattern in patterns)
        ]

        # Resolve the phrase "add user ... to group" as grant_access even
        # though the words "user" and "group" could otherwise resemble
        # creation requests. Likewise for remove-from-group.
        if IntentType.GRANT_ACCESS in matched:
            return IntentType.GRANT_ACCESS
        if IntentType.REVOKE_ACCESS in matched:
            return IntentType.REVOKE_ACCESS

        unique = list(dict.fromkeys(matched))
        return unique[0] if len(unique) == 1 else None

    @staticmethod
    def _normalize_llm_backend(value: Any) -> ExecutionBackend | None:
        if isinstance(value, ExecutionBackend):
            return value
        if not isinstance(value, str):
            return None

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
        return aliases.get(value.strip().casefold())

    @classmethod
    def _extract_membership_metadata(
        cls,
        user_input: str,
    ) -> dict[str, str | None]:
        match = cls.MEMBERSHIP_PATTERN.search(user_input)
        if match is None:
            return {}

        raw_user = match.group("user").strip()
        group_name = match.group("group").strip()
        result: dict[str, str | None] = {
            "group_name": group_name,
        }

        if "@" in raw_user:
            local_part = raw_user.split("@", maxsplit=1)[0].strip()
            result.update(
                {
                    "email": raw_user,
                    "username": local_part or None,
                    "username_source": "derived_from_email" if local_part else None,
                }
            )
        else:
            result.update(
                {
                    "username": raw_user,
                    "username_source": "explicit",
                }
            )

        return result

    @classmethod
    def _extract_explicit_email(cls, user_input: str) -> str | None:
        """Extract an email written by the user, independent of the LLM."""
        match = cls.EXPLICIT_EMAIL_PATTERN.search(user_input)
        return match.group("email") if match else None

    @staticmethod
    def _extract_response_text(content: Any) -> str:
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

        raise ValueError("The model returned empty or unsupported response content.")

    @staticmethod
    def _remove_markdown_fences(response_text: str) -> str:
        cleaned = re.sub(
            r"^```(?:json)?\s*",
            "",
            response_text.strip(),
            flags=re.IGNORECASE,
        )
        return re.sub(r"\s*```$", "", cleaned).strip()

    @classmethod
    def _extract_json_object(cls, response_text: str) -> dict[str, Any]:
        cleaned = cls._remove_markdown_fences(response_text)
        if not cleaned:
            raise ValueError("The model returned an empty response.")

        try:
            parsed = json.loads(cleaned)
            if isinstance(parsed, dict) and "intent" in parsed:
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

        raise ValueError("No valid intent JSON object was found in the model response.")

    @classmethod
    def _prepare_result(
        cls,
        *,
        raw_result: dict[str, Any],
        user_input: str,
    ) -> dict[str, Any]:
        raw_metadata = raw_result.get("metadata")
        if not isinstance(raw_metadata, dict):
            raw_metadata = {}

        normalized_metadata = {
            field: cls._normalize_optional_string(raw_metadata.get(field))
            for field in cls.STRING_METADATA_FIELDS
        }

        explicit_email = cls._extract_explicit_email(user_input)
        if explicit_email:
            normalized_metadata["email"] = explicit_email
            normalized_metadata["username"] = explicit_email.split("@", 1)[0]
            normalized_metadata["username_source"] = "explicit_email"
            logger.info(
                "EXPLICIT_EMAIL_RESOLVED | email={} | source=user_input",
                explicit_email,
            )

        normalized_metadata["cpu_count"] = cls._normalize_integer(
            raw_metadata.get("cpu_count")
        )
        normalized_metadata["ram_gb"] = cls._normalize_integer(
            raw_metadata.get("ram_gb")
        )

        model_intent = IntentType(
            cls._normalize_intent(raw_result.get("intent"))
        )
        deterministic_intent = cls._detect_deterministic_intent(user_input)
        selected_intent = deterministic_intent or model_intent

        explicit_email_match = cls.EXPLICIT_EMAIL_PATTERN.search(user_input)
        if explicit_email_match:
            explicit_email = explicit_email_match.group(0).casefold()
            normalized_metadata["email"] = explicit_email
            normalized_metadata["username"] = explicit_email.split(
                "@",
                maxsplit=1,
            )[0]
            normalized_metadata["username_source"] = "derived_from_email"
        elif (
            selected_intent in {
                IntentType.GET_USER_DETAILS,
                IntentType.PASSWORD_RESET,
                IntentType.FAILED_LOGIN_INVESTIGATION,
            }
            and not normalized_metadata.get("username")
            and not normalized_metadata.get("email")
        ):
            username_match = cls.EXPLICIT_DETAILS_USERNAME_PATTERN.search(
                user_input
            )
            if username_match is None:
                username_match = cls.EXPLICIT_TARGET_PATTERN.search(user_input)
            if (
                username_match is None
                and selected_intent is IntentType.FAILED_LOGIN_INVESTIGATION
            ):
                username_match = cls.EXPLICIT_LOCKOUT_USERNAME_PATTERN.search(
                    user_input
                )
            if username_match:
                normalized_metadata["username"] = username_match.group(1)
                normalized_metadata["username_source"] = "explicit"

        membership_metadata = cls._extract_membership_metadata(user_input)
        if selected_intent in {IntentType.GRANT_ACCESS, IntentType.REVOKE_ACCESS}:
            for key, value in membership_metadata.items():
                if value is not None:
                    normalized_metadata[key] = value

        explicit_backend = cls._detect_explicit_execution_backend(user_input)
        llm_backend = cls._normalize_llm_backend(
            raw_metadata.get("execution_backend")
        )
        selected_backend = explicit_backend or llm_backend
        default_api_applied = False

        if selected_backend is None and selected_intent in cls.DEFAULT_API_INTENTS:
            selected_backend = ExecutionBackend.API
            default_api_applied = True

        normalized_metadata["execution_backend"] = (
            selected_backend.value if selected_backend is not None else None
        )

        # These values must come from trusted controls, never the LLM.
        normalized_metadata["approval_granted"] = False
        normalized_metadata["initial_password"] = None
        normalized_metadata["domain_password"] = None
        normalized_metadata["admin_password"] = None

        model_confidence = cls._normalize_confidence(raw_result.get("confidence"))
        if deterministic_intent is not None:
            confidence = max(model_confidence, 0.99)
            confidence_source = "deterministic_classification"
        else:
            confidence = model_confidence
            confidence_source = "model"

        explanation = raw_result.get("explanation")
        invalid_explanation = (
            not isinstance(explanation, str)
            or not explanation.strip()
            or explanation.strip().casefold() in {"none", "null", "n/a"}
            or model_intent is not selected_intent
        )
        if invalid_explanation:
            explanation = f"Explicit request classified as {selected_intent.value}."

        logger.info(
            "INTENT_RESOLVED | model_intent={} | deterministic_intent={} | "
            "selected_intent={} | model_confidence={} | final_confidence={} | source={}",
            model_intent.value,
            deterministic_intent.value if deterministic_intent else None,
            selected_intent.value,
            model_confidence,
            confidence,
            confidence_source,
        )
        logger.info(
            "EXECUTION_BACKEND_RESOLVED | explicit_backend={} | llm_backend={} | "
            "selected_backend={} | default_api_applied={}",
            explicit_backend.value if explicit_backend else None,
            llm_backend.value if llm_backend else None,
            selected_backend.value if selected_backend else None,
            default_api_applied,
        )

        return {
            "success": True,
            "intent": selected_intent.value,
            "confidence": confidence,
            "explanation": explanation.strip(),
            "metadata": normalized_metadata,
            "error": None,
        }

    @staticmethod
    def _normalize_optional_string(value: Any) -> str | None:
        if value is None:
            return None
        normalized = str(value).strip()
        if normalized.casefold() in {
            "",
            "null",
            "none",
            "n/a",
            "na",
            "not provided",
            "not available",
        }:
            return None
        return normalized

    @staticmethod
    def _normalize_integer(value: Any) -> int | None:
        if value is None or (isinstance(value, str) and not value.strip()):
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _normalize_intent(value: Any) -> str:
        if not isinstance(value, str):
            return IntentType.UNKNOWN.value
        normalized = value.strip().casefold()
        supported = {intent.value for intent in IntentType}
        return normalized if normalized in supported else IntentType.UNKNOWN.value

    @staticmethod
    def _normalize_confidence(value: Any) -> float:
        try:
            confidence = float(value)
        except (TypeError, ValueError):
            return 0.0
        return max(0.0, min(1.0, confidence))

    @staticmethod
    def _derive_username_from_email(
        result: UnifiedExtractionResult,
    ) -> UnifiedExtractionResult:
        metadata = result.metadata

        if metadata.username:
            source = metadata.username_source
            if not source:
                source = "derived_from_email" if metadata.email else "explicit"
            return result.model_copy(
                update={
                    "metadata": metadata.model_copy(
                        update={"username_source": source}
                    )
                }
            )

        if not metadata.email or "@" not in metadata.email:
            return result

        local_part = metadata.email.split("@", maxsplit=1)[0].strip()
        if not local_part:
            return result

        logger.info(
            "UNIFIED_EXTRACTION_DERIVED_FIELD | field=username | source=email | username={}",
            local_part,
        )
        return result.model_copy(
            update={
                "metadata": metadata.model_copy(
                    update={
                        "username": local_part,
                        "username_source": "derived_from_email",
                    }
                )
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
        metadata: dict[str, Any] | IdentityMetadata,
        intent: str,
    ) -> tuple[bool, str]:
        try:
            validated = (
                metadata
                if isinstance(metadata, IdentityMetadata)
                else IdentityMetadata.model_validate(metadata)
            )
        except ValidationError:
            return False, "Extracted metadata is invalid."

        if intent == IntentType.UNKNOWN.value:
            return False, "The intent is unsupported."

        if intent == IntentType.GET_USER_DETAILS.value and not (
            validated.username or validated.email or validated.user_id
        ):
            return False, "Username, email, or user ID is required."

        return (
            True,
            "Final operation readiness validation will be performed by IdentityAgent.",
        )

    def get_supported_intents(self) -> list[str]:
        return [
            intent.value
            for intent in IntentType
            if intent is not IntentType.UNKNOWN
        ]
