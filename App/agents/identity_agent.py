"""
Identity Agent Module

Purpose:
    Validate Identity operation readiness, derive a username from an
    explicitly supplied email when necessary, ask for missing
    information, select the correct MCP server and execute the correct
    MCP tool.

Supported operations:
    - Password reset through Microsoft Graph or PowerShell
    - Get user details through Microsoft Graph or PowerShell
    - Account unlock through PowerShell
    - Grant access through PowerShell
    - Revoke access through PowerShell
    - Failed-login investigation
    - Create Active Directory user through PowerShell
    - Delete Active Directory user through PowerShell
    - Create Active Directory group through PowerShell
    - Create Hyper-V virtual machine through PowerShell
"""

from __future__ import annotations

import asyncio
import re
from typing import Any

from loguru import logger
from pydantic import ValidationError

from App.mcp_client.identity_mcp_client import IdentityMCPClient
from App.workflow.state import (
    AgentExecutionResult,
    ExecutionBackend,
    IdentityMetadata,
    IntentType,
    MetadataValidationResult,
    ToolName,
    ToolResult,
)


class IdentityAgent:
    """Identity and access-management agent using deterministic MCP routing."""

    EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

    REQUIRED_FIELDS: dict[IntentType, tuple[str, ...]] = {
        IntentType.PASSWORD_RESET: (
            "username",
            "execution_backend",
        ),
        IntentType.ACCOUNT_UNLOCK: (
            "username",
        ),
        IntentType.GRANT_ACCESS: (
            "username",
            "group_name",
        ),
        IntentType.REVOKE_ACCESS: (
            "username",
            "group_name",
        ),
        IntentType.GET_USER_DETAILS: (
            "username",
            "execution_backend",
        ),
        IntentType.FAILED_LOGIN_INVESTIGATION: (
            "username",
        ),
        IntentType.CREATE_USER: (
            "first_name",
            "last_name",
            "username",
            "email",
            "department",
            "initial_password",
        ),
        IntentType.DELETE_USER: (
            "first_name",
            "last_name",
            "username",
        ),
        IntentType.CREATE_GROUP: (
            "group_name",
        ),
        IntentType.CREATE_VM: (
            "target_host",
            "vm_name",
            "cpu_count",
            "ram_gb",
            "vswitch_name",
            "hostname",
            "admin_password",
        ),
    }

    TOOL_NAMES: dict[IntentType, ToolName] = {
        IntentType.PASSWORD_RESET: ToolName.RESET_PASSWORD,
        IntentType.ACCOUNT_UNLOCK: ToolName.UNLOCK_ACCOUNT,
        IntentType.GRANT_ACCESS: ToolName.MANAGE_ACCESS,
        IntentType.REVOKE_ACCESS: ToolName.MANAGE_ACCESS,
        IntentType.GET_USER_DETAILS: ToolName.GET_USER_DETAILS,
        IntentType.FAILED_LOGIN_INVESTIGATION: ToolName.INVESTIGATE_FAILED_LOGIN,
        IntentType.CREATE_USER: ToolName.CREATE_USER,
        IntentType.DELETE_USER: ToolName.DELETE_USER,
        IntentType.CREATE_GROUP: ToolName.CREATE_GROUP,
        IntentType.CREATE_VM: ToolName.CREATE_VM,
    }

    APPROVAL_REQUIRED_INTENTS: set[IntentType] = {
        IntentType.DELETE_USER,
        IntentType.REVOKE_ACCESS,
    }

    FIELD_LABELS: dict[str, str] = {
        "username": "username",
        "email": "email address",
        "user_id": "user ID",
        "employee_number": "employee number",
        "group_name": "group name",
        "time_window": "time window",
        "execution_backend": "execution method, either API or script",
        "first_name": "first name",
        "last_name": "last name",
        "department": "department",
        "target_ou": "target organizational unit",
        "description": "group description",
        "initial_password": "initial password",
        "target_host": "target Hyper-V host",
        "vm_name": "virtual machine name",
        "cpu_count": "CPU count",
        "ram_gb": "RAM in GB",
        "vswitch_name": "virtual switch name",
        "hostname": "hostname",
        "admin_password": "virtual-machine administrator password",
        "approval_granted": "explicit authorization approval",
    }

    SENSITIVE_FIELDS: set[str] = {
        "initial_password",
        "domain_password",
        "admin_password",
    }

    def __init__(
        self,
        *,
        mcp_client: IdentityMCPClient | None = None,
    ) -> None:
        self.mcp_client = mcp_client or IdentityMCPClient()

        logger.info(
            "IdentityAgent initialized in MCP mode | supported_operations={}",
            self.get_supported_operations(),
        )

    @staticmethod
    def _normalize_intent(operation: str | IntentType) -> IntentType:
        if isinstance(operation, IntentType):
            return operation

        if not isinstance(operation, str):
            return IntentType.UNKNOWN

        try:
            return IntentType(operation.strip().casefold())
        except ValueError:
            return IntentType.UNKNOWN

    @classmethod
    def _derive_username_from_email(
        cls,
        metadata: IdentityMetadata,
    ) -> tuple[IdentityMetadata, list[str]]:
        if metadata.username:
            return (
                metadata.model_copy(
                    update={
                        "username_source": metadata.username_source or "explicit",
                    }
                ),
                [],
            )

        if not metadata.email or not cls.EMAIL_PATTERN.fullmatch(metadata.email):
            return metadata, []

        username = metadata.email.split("@", maxsplit=1)[0].strip()
        if not username:
            return metadata, []

        updated_metadata = metadata.model_copy(
            update={
                "username": username,
                "username_source": "derived_from_email",
            }
        )

        logger.info(
            "IDENTITY_METADATA_DERIVED | field=username | source=email | username={}",
            username,
        )

        return updated_metadata, ["username"]

    @classmethod
    def _validate_metadata(
        cls,
        *,
        intent: IntentType,
        metadata: IdentityMetadata,
        derived_fields: list[str],
    ) -> MetadataValidationResult:
        """Validate required fields and operation-specific approvals."""

        required_fields = cls.REQUIRED_FIELDS.get(intent)
        if required_fields is None:
            return MetadataValidationResult(
                is_valid=False,
                missing_fields=[],
                derived_fields=derived_fields,
                message=(
                    "No Identity Agent validation policy is configured for "
                    f"intent '{intent.value}'."
                ),
            )

        missing_fields: list[str] = []

        for field_name in required_fields:
            field_value = getattr(metadata, field_name, None)

            if field_value is None:
                missing_fields.append(field_name)
                continue

            if isinstance(field_value, str) and not field_value.strip():
                missing_fields.append(field_name)

        if (
            intent in cls.APPROVAL_REQUIRED_INTENTS
            and not metadata.approval_granted
            and "approval_granted" not in missing_fields
        ):
            missing_fields.append("approval_granted")

        if (
            intent is IntentType.PASSWORD_RESET
            and metadata.execution_backend == ExecutionBackend.SCRIPT
            and not metadata.approval_granted
            and "approval_granted" not in missing_fields
        ):
            missing_fields.append("approval_granted")

        if intent is IntentType.CREATE_VM:
            if (
                metadata.cpu_count is not None
                and metadata.cpu_count < 1
                and "cpu_count" not in missing_fields
            ):
                missing_fields.append("cpu_count")

            if (
                metadata.ram_gb is not None
                and metadata.ram_gb < 1
                and "ram_gb" not in missing_fields
            ):
                missing_fields.append("ram_gb")

        if missing_fields:
            return MetadataValidationResult(
                is_valid=False,
                missing_fields=missing_fields,
                derived_fields=derived_fields,
                message=(
                    "Additional information or approval is required before "
                    "the selected MCP tool can be called."
                ),
            )

        return MetadataValidationResult(
            is_valid=True,
            missing_fields=[],
            derived_fields=derived_fields,
            message="Metadata is valid.",
        )

    @classmethod
    def _build_clarification_question(cls, missing_fields: list[str]) -> str:
        labels = [cls.FIELD_LABELS.get(name, name) for name in missing_fields]

        if not labels:
            return "Please provide the required operation information."

        if len(labels) == 1:
            if missing_fields[0] == "approval_granted":
                return (
                    "This operation requires explicit authorization approval. "
                    "Please approve the operation before continuing."
                )
            return f"Please provide the {labels[0]}."

        if len(labels) == 2:
            return (
                "Please provide the following missing information: "
                f"{labels[0]} and {labels[1]}."
            )

        joined_labels = ", ".join(labels[:-1]) + f", and {labels[-1]}"
        return f"Please provide the following missing information: {joined_labels}."

    @staticmethod
    def _build_mcp_arguments(
        *,
        intent: IntentType,
        metadata: IdentityMetadata,
        request_id: str,
        correlation_id: str,
    ) -> dict[str, Any]:
        arguments: dict[str, Any] = {
            "request_id": request_id,
            "correlation_id": correlation_id,
        }

        arguments.update(
            metadata.model_dump(
                mode="json",
                exclude_none=True,
            )
        )

        if intent is IntentType.GRANT_ACCESS:
            arguments["action"] = "grant"
        elif intent is IntentType.REVOKE_ACCESS:
            arguments["action"] = "revoke"

        return arguments

    @classmethod
    def _safe_metadata_for_logging(
        cls,
        metadata: IdentityMetadata,
    ) -> dict[str, Any]:
        data = metadata.model_dump(mode="json", exclude_none=True)

        for sensitive_field in cls.SENSITIVE_FIELDS:
            if sensitive_field in data:
                data[sensitive_field] = "[REDACTED]"

        return data

    def execute(
        self,
        operation: str | IntentType,
        metadata: dict[str, Any] | IdentityMetadata,
        *,
        request_id: str = "untracked",
        correlation_id: str = "untracked",
    ) -> AgentExecutionResult:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(
                self.execute_async(
                    operation=operation,
                    metadata=metadata,
                    request_id=request_id,
                    correlation_id=correlation_id,
                )
            )

        raise RuntimeError(
            "IdentityAgent.execute() cannot run inside an active event loop. "
            "Use 'await IdentityAgent.execute_async(...)'."
        )

    async def execute_async(
        self,
        operation: str | IntentType,
        metadata: dict[str, Any] | IdentityMetadata,
        *,
        request_id: str = "untracked",
        correlation_id: str = "untracked",
    ) -> AgentExecutionResult:
        intent = self._normalize_intent(operation)

        try:
            validated_metadata = (
                metadata
                if isinstance(metadata, IdentityMetadata)
                else IdentityMetadata.model_validate(metadata)
            )
        except ValidationError as exc:
            logger.warning(
                "IDENTITY_METADATA_INVALID | request_id={} | correlation_id={} | error_count={}",
                request_id,
                correlation_id,
                exc.error_count(),
            )

            validation = MetadataValidationResult(
                is_valid=False,
                missing_fields=[],
                derived_fields=[],
                message="The extracted metadata did not match the required schema.",
            )

            return AgentExecutionResult(
                success=False,
                intent=intent,
                selected_agent="identity_agent",
                selected_tool=None,
                metadata=IdentityMetadata(),
                validation=validation,
                tool_result=None,
                clarification_required=False,
                clarification_question=None,
                message=validation.message,
                error="Metadata validation failed",
            )

        logger.info(
            "IDENTITY_AGENT_RECEIVED | request_id={} | correlation_id={} | "
            "intent={} | metadata={}",
            request_id,
            correlation_id,
            intent.value,
            self._safe_metadata_for_logging(validated_metadata),
        )

        if intent is IntentType.UNKNOWN:
            validation = MetadataValidationResult(
                is_valid=False,
                missing_fields=[],
                derived_fields=[],
                message="The requested operation is not supported by the Identity Agent.",
            )

            return AgentExecutionResult(
                success=False,
                intent=IntentType.UNKNOWN,
                selected_agent="identity_agent",
                selected_tool=None,
                metadata=validated_metadata,
                validation=validation,
                tool_result=None,
                clarification_required=False,
                clarification_question=None,
                message=validation.message,
                error="Unsupported identity operation",
            )

        validated_metadata, derived_fields = self._derive_username_from_email(
            validated_metadata
        )

        validation = self._validate_metadata(
            intent=intent,
            metadata=validated_metadata,
            derived_fields=derived_fields,
        )

        if not validation.is_valid:
            clarification_question = self._build_clarification_question(
                validation.missing_fields
            )

            logger.info(
                "IDENTITY_AGENT_NEEDS_INPUT | request_id={} | correlation_id={} | "
                "intent={} | missing_fields={} | derived_fields={}",
                request_id,
                correlation_id,
                intent.value,
                validation.missing_fields,
                validation.derived_fields,
            )

            return AgentExecutionResult(
                success=False,
                intent=intent,
                selected_agent="identity_agent",
                selected_tool=None,
                metadata=validated_metadata,
                validation=validation,
                tool_result=None,
                clarification_required=True,
                clarification_question=clarification_question,
                message=clarification_question,
                error=None,
            )

        selected_tool_name = self.TOOL_NAMES.get(intent)
        if selected_tool_name is None:
            return AgentExecutionResult(
                success=False,
                intent=intent,
                selected_agent="identity_agent",
                selected_tool=None,
                metadata=validated_metadata,
                validation=validation,
                tool_result=None,
                clarification_required=False,
                clarification_question=None,
                message=f"No MCP tool is registered for '{intent.value}'.",
                error="MCP tool not registered",
            )

        server_module = self.mcp_client.SERVER_MODULES.get(intent.value)
        mcp_tool_name = self.mcp_client.TOOL_NAMES.get(intent.value)

        if server_module is None or mcp_tool_name is None:
            return AgentExecutionResult(
                success=False,
                intent=intent,
                selected_agent="identity_agent",
                selected_tool=selected_tool_name,
                metadata=validated_metadata,
                validation=validation,
                tool_result=None,
                clarification_required=False,
                clarification_question=None,
                message=(
                    "The selected operation does not have a complete MCP "
                    "server registration."
                ),
                error="Incomplete MCP registration",
            )

        mcp_arguments = self._build_mcp_arguments(
            intent=intent,
            metadata=validated_metadata,
            request_id=request_id,
            correlation_id=correlation_id,
        )

        logger.info(
            "MCP_TOOL_DISPATCH | request_id={} | correlation_id={} | intent={} | "
            "selected_agent=identity_agent | selected_server={} | mcp_tool={} | "
            "application_tool={} | argument_fields={}",
            request_id,
            correlation_id,
            intent.value,
            server_module,
            mcp_tool_name,
            selected_tool_name.value,
            sorted(mcp_arguments.keys()),
        )

        try:
            mcp_result = await self.mcp_client.call_tool(
                operation=intent.value,
                arguments=mcp_arguments,
            )

            tool_result_data = mcp_result.model_dump(mode="json")
            if not tool_result_data.get("operation_id"):
                tool_result_data.pop("operation_id", None)

            tool_result = ToolResult.model_validate(tool_result_data)
        except Exception as exc:
            logger.exception(
                "MCP_TOOL_EXECUTION_FAILED | request_id={} | correlation_id={} | "
                "intent={} | selected_server={} | mcp_tool={} | error_type={}",
                request_id,
                correlation_id,
                intent.value,
                server_module,
                mcp_tool_name,
                type(exc).__name__,
            )

            return AgentExecutionResult(
                success=False,
                intent=intent,
                selected_agent="identity_agent",
                selected_tool=selected_tool_name,
                metadata=validated_metadata,
                validation=validation,
                tool_result=None,
                clarification_required=False,
                clarification_question=None,
                message="The selected Identity MCP tool could not be executed.",
                error=type(exc).__name__,
            )

        logger.info(
            "MCP_TOOL_COMPLETED | request_id={} | correlation_id={} | intent={} | "
            "selected_server={} | mcp_tool={} | application_tool={} | "
            "tool_status={} | tool_success={} | operation_id={}",
            request_id,
            correlation_id,
            intent.value,
            server_module,
            mcp_tool_name,
            tool_result.tool_name.value,
            tool_result.status.value,
            tool_result.success,
            tool_result.operation_id,
        )

        return AgentExecutionResult(
            success=tool_result.success,
            intent=intent,
            selected_agent="identity_agent",
            selected_tool=tool_result.tool_name,
            metadata=validated_metadata,
            validation=validation,
            tool_result=tool_result,
            clarification_required=False,
            clarification_question=None,
            message=tool_result.message,
            error=tool_result.error,
        )

    def get_supported_operations(self) -> list[str]:
        """Return all Identity operations registered through MCP."""
        return sorted(intent.value for intent in self.TOOL_NAMES)
