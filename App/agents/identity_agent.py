from __future__ import annotations

import asyncio
import re
from typing import Any
from loguru import logger

from App.mcp_client.identity_mcp_client import IdentityMCPClient
from App.workflow.state import AgentExecutionResult, IdentityMetadata, IntentType, MetadataValidationResult, ToolName, ToolResult


class IdentityAgent:
    EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

    REQUIRED_FIELDS = {
        IntentType.PASSWORD_RESET: ("username", "email", "employee_number"),
        IntentType.ACCOUNT_UNLOCK: ("username", "email", "employee_number"),
        IntentType.GRANT_ACCESS: ("username", "email", "employee_number", "group_name"),
        IntentType.REVOKE_ACCESS: ("username", "email", "employee_number", "group_name"),
        IntentType.GET_USER_DETAILS: ("username",),
        IntentType.FAILED_LOGIN_INVESTIGATION: ("username", "email", "employee_number"),
    }

    TOOL_NAMES = {
        IntentType.PASSWORD_RESET: ToolName.RESET_PASSWORD,
        IntentType.ACCOUNT_UNLOCK: ToolName.UNLOCK_ACCOUNT,
        IntentType.GRANT_ACCESS: ToolName.MANAGE_ACCESS,
        IntentType.REVOKE_ACCESS: ToolName.MANAGE_ACCESS,
        IntentType.GET_USER_DETAILS: ToolName.GET_USER_DETAILS,
        IntentType.FAILED_LOGIN_INVESTIGATION: ToolName.INVESTIGATE_FAILED_LOGIN,
    }

    FIELD_LABELS = {
        "username": "username",
        "email": "email address",
        "user_id": "user ID",
        "employee_number": "employee number",
        "group_name": "group name",
        "time_window": "time window",
    }

    def __init__(self, *, mcp_client: IdentityMCPClient | None = None) -> None:
        self.mcp_client = mcp_client or IdentityMCPClient()
        logger.info("IdentityAgent initialized in MCP mode | supported_operations={}", self.get_supported_operations())

    @staticmethod
    def _normalize_intent(operation: str | IntentType) -> IntentType:
        if isinstance(operation, IntentType):
            return operation
        try:
            return IntentType(operation.strip())
        except (ValueError, AttributeError):
            return IntentType.UNKNOWN

    @classmethod
    def _derive_username_from_email(cls, metadata: IdentityMetadata) -> tuple[IdentityMetadata, list[str]]:
        if metadata.username:
            return metadata.model_copy(update={"username_source": metadata.username_source or "explicit"}), []
        if metadata.email and cls.EMAIL_PATTERN.fullmatch(metadata.email):
            username = metadata.email.split("@", 1)[0].strip()
            return metadata.model_copy(update={"username": username, "username_source": "derived_from_email"}), ["username"]
        return metadata, []

    @classmethod
    def _validate_metadata(cls, *, intent: IntentType, metadata: IdentityMetadata, derived_fields: list[str]) -> MetadataValidationResult:
        required = cls.REQUIRED_FIELDS.get(intent, ())
        missing = [name for name in required if getattr(metadata, name) is None]
        return MetadataValidationResult(
            is_valid=bool(required) and not missing,
            missing_fields=missing,
            derived_fields=derived_fields,
            message="Metadata is valid." if required and not missing else "Additional information is required before the selected MCP tool can be called.",
        )

    @classmethod
    def _build_clarification_question(cls, missing_fields: list[str]) -> str:
        labels = [cls.FIELD_LABELS.get(name, name) for name in missing_fields]
        if not labels:
            return "Please provide the required identity information."
        if len(labels) == 1:
            return f"Please provide the {labels[0]}."
        if len(labels) == 2:
            return f"Please provide the following missing information: {labels[0]} and {labels[1]}."
        return "Please provide the following missing information: " + ", ".join(labels[:-1]) + f", and {labels[-1]}."

    @staticmethod
    def _build_arguments(*, intent: IntentType, metadata: IdentityMetadata, request_id: str, correlation_id: str) -> dict[str, Any]:
        arguments = metadata.model_dump(mode="json", exclude_none=True)
        arguments.update({"request_id": request_id, "correlation_id": correlation_id})
        if intent is IntentType.GRANT_ACCESS:
            arguments["action"] = "grant"
        elif intent is IntentType.REVOKE_ACCESS:
            arguments["action"] = "revoke"
        return arguments

    def execute(self, operation: str | IntentType, metadata: dict | IdentityMetadata, *, request_id: str = "untracked", correlation_id: str = "untracked") -> AgentExecutionResult:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self.execute_async(operation, metadata, request_id=request_id, correlation_id=correlation_id))
        raise RuntimeError("Use await execute_async() inside an active event loop.")

    async def execute_async(self, operation: str | IntentType, metadata: dict | IdentityMetadata, *, request_id: str = "untracked", correlation_id: str = "untracked") -> AgentExecutionResult:
        intent = self._normalize_intent(operation)
        validated = metadata if isinstance(metadata, IdentityMetadata) else IdentityMetadata.model_validate(metadata)
        if intent is IntentType.UNKNOWN:
            validation = MetadataValidationResult(is_valid=False, missing_fields=[], derived_fields=[], message="The requested operation is not supported by the Identity Agent.")
            return AgentExecutionResult(success=False, intent=intent, selected_agent="identity_agent", selected_tool=None, metadata=validated, validation=validation, tool_result=None, clarification_required=False, clarification_question=None, message=validation.message, error="Unsupported identity operation")

        validated, derived = self._derive_username_from_email(validated)
        validation = self._validate_metadata(intent=intent, metadata=validated, derived_fields=derived)
        if not validation.is_valid:
            question = self._build_clarification_question(validation.missing_fields)
            return AgentExecutionResult(success=False, intent=intent, selected_agent="identity_agent", selected_tool=None, metadata=validated, validation=validation, tool_result=None, clarification_required=True, clarification_question=question, message=question, error=None)

        selected_tool = self.TOOL_NAMES.get(intent)
        arguments = self._build_arguments(intent=intent, metadata=validated, request_id=request_id, correlation_id=correlation_id)
        logger.info("MCP_TOOL_DISPATCH | request_id={} | correlation_id={} | intent={} | selected_server={} | selected_mcp_tool={} | application_tool={}", request_id, correlation_id, intent.value, self.mcp_client.SERVER_MODULES.get(intent.value), self.mcp_client.TOOL_NAMES.get(intent.value), selected_tool.value if selected_tool else None)
        try:
            mcp_result = await self.mcp_client.call_tool(operation=intent.value, arguments=arguments)
            tool_result = ToolResult.model_validate(mcp_result.model_dump())
        except Exception as exc:
            logger.exception("MCP_TOOL_EXECUTION_FAILED | request_id={} | correlation_id={} | intent={} | error_type={}", request_id, correlation_id, intent.value, type(exc).__name__)
            return AgentExecutionResult(success=False, intent=intent, selected_agent="identity_agent", selected_tool=selected_tool, metadata=validated, validation=validation, tool_result=None, clarification_required=False, clarification_question=None, message="The selected Identity MCP tool could not be executed.", error=type(exc).__name__)

        logger.info("MCP_TOOL_COMPLETED | request_id={} | correlation_id={} | intent={} | application_tool={} | status={} | operation_id={}", request_id, correlation_id, intent.value, tool_result.tool_name.value, tool_result.status.value, tool_result.operation_id)
        return AgentExecutionResult(success=tool_result.success, intent=intent, selected_agent="identity_agent", selected_tool=tool_result.tool_name, metadata=validated, validation=validation, tool_result=tool_result, clarification_required=False, clarification_question=None, message=tool_result.message, error=tool_result.error)

    def get_supported_operations(self) -> list[str]:
        return sorted(intent.value for intent in self.TOOL_NAMES)
