"""
Identity Agent Module

Purpose:
    Validate Identity operation readiness, derive a username from an
    explicitly supplied email when necessary, ask for missing
    information, select the correct MCP server and execute the correct
    MCP tool.
"""

from __future__ import annotations

import asyncio
import re
from typing import Any

from loguru import logger

from App.mcp_client.identity_mcp_client import (
    IdentityMCPClient,
)
from App.workflow.state import (
    AgentExecutionResult,
    IdentityMetadata,
    IntentType,
    MetadataValidationResult,
    ToolName,
    ToolResult,
)


class IdentityAgent:
    """
    Identity and Access Management agent.

    Responsibilities:

    1. Normalize and validate the classified intent.
    2. Normalize Pydantic identity metadata.
    3. Derive username from an explicitly supplied email.
    4. Determine whether mandatory information is present.
    5. Ask for missing information without calling MCP.
    6. Select one MCP server and one MCP tool deterministically.
    7. Call the selected MCP tool.
    8. Validate the MCP result as a Pydantic ToolResult.
    9. Log MCP dispatch and execution evidence.
    """

    EMAIL_PATTERN = re.compile(
        r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
    )

    REQUIRED_FIELDS: dict[
        IntentType,
        tuple[str, ...],
    ] = {
        IntentType.PASSWORD_RESET: (
            "username",
            "email",
            "employee_number",
        ),

        IntentType.ACCOUNT_UNLOCK: (
            "username",
            "email",
            "employee_number",
        ),

        IntentType.GRANT_ACCESS: (
            "username",
            "email",
            "employee_number",
            "group_name",
        ),

        IntentType.REVOKE_ACCESS: (
            "username",
            "email",
            "employee_number",
            "group_name",
        ),

        IntentType.GET_USER_DETAILS: (
            "username",
        ),

        IntentType.FAILED_LOGIN_INVESTIGATION: (
            "username",
            "email",
            "employee_number",
        ),
    }

    TOOL_NAMES: dict[
        IntentType,
        ToolName,
    ] = {
        IntentType.PASSWORD_RESET:
            ToolName.RESET_PASSWORD,

        IntentType.ACCOUNT_UNLOCK:
            ToolName.UNLOCK_ACCOUNT,

        IntentType.GRANT_ACCESS:
            ToolName.MANAGE_ACCESS,

        IntentType.REVOKE_ACCESS:
            ToolName.MANAGE_ACCESS,

        IntentType.GET_USER_DETAILS:
            ToolName.GET_USER_DETAILS,

        IntentType.FAILED_LOGIN_INVESTIGATION:
            ToolName.INVESTIGATE_FAILED_LOGIN,
    }

    FIELD_LABELS: dict[str, str] = {
        "username": "username",
        "email": "email address",
        "user_id": "user ID",
        "employee_number": "employee number",
        "group_name": "group name",
        "time_window": "time window",
    }

    def __init__(
        self,
        *,
        mcp_client: IdentityMCPClient | None = None,
    ) -> None:
        self.mcp_client = (
            mcp_client
            if mcp_client is not None
            else IdentityMCPClient()
        )

        logger.info(
            "IdentityAgent initialized in MCP mode | "
            "supported_operations={}",
            self.get_supported_operations(),
        )

    @staticmethod
    def _normalize_intent(
        operation: str | IntentType,
    ) -> IntentType:
        if isinstance(
            operation,
            IntentType,
        ):
            return operation

        try:
            return IntentType(
                operation.strip()
            )

        except (
            ValueError,
            AttributeError,
        ):
            return IntentType.UNKNOWN

    @classmethod
    def _derive_username_from_email(
        cls,
        metadata: IdentityMetadata,
    ) -> tuple[
        IdentityMetadata,
        list[str],
    ]:
        """
        Derive username from an explicitly supplied email.

        Example:

            Shreesanyog.Rath@Coforge.com

        becomes:

            Shreesanyog.Rath
        """

        if metadata.username:
            return (
                metadata.model_copy(
                    update={
                        "username_source": (
                            metadata.username_source
                            or "explicit"
                        )
                    }
                ),
                [],
            )

        if not metadata.email:
            return metadata, []

        if not cls.EMAIL_PATTERN.fullmatch(
            metadata.email
        ):
            return metadata, []

        username = metadata.email.split(
            "@",
            maxsplit=1,
        )[0].strip()

        if not username:
            return metadata, []

        updated_metadata = metadata.model_copy(
            update={
                "username": username,
                "username_source":
                    "derived_from_email",
            }
        )

        logger.info(
            "IDENTITY_METADATA_DERIVED | "
            "field=username | source=email | "
            "username={}",
            username,
        )

        return (
            updated_metadata,
            ["username"],
        )

    @classmethod
    def _validate_metadata(
        cls,
        *,
        intent: IntentType,
        metadata: IdentityMetadata,
        derived_fields: list[str],
    ) -> MetadataValidationResult:
        required_fields = (
            cls.REQUIRED_FIELDS.get(
                intent,
                tuple(),
            )
        )

        if not required_fields:
            return MetadataValidationResult(
                is_valid=False,
                missing_fields=[],
                derived_fields=derived_fields,
                message=(
                    f"No Identity Agent validation policy "
                    f"is configured for intent "
                    f"'{intent.value}'."
                ),
            )

        missing_fields = [
            field_name
            for field_name in required_fields
            if getattr(
                metadata,
                field_name,
            )
            is None
        ]

        if missing_fields:
            return MetadataValidationResult(
                is_valid=False,
                missing_fields=missing_fields,
                derived_fields=derived_fields,
                message=(
                    "Additional information is required "
                    "before the selected MCP tool can be "
                    "called."
                ),
            )

        return MetadataValidationResult(
            is_valid=True,
            missing_fields=[],
            derived_fields=derived_fields,
            message="Metadata is valid.",
        )

    @classmethod
    def _build_clarification_question(
        cls,
        missing_fields: list[str],
    ) -> str:
        labels = [
            cls.FIELD_LABELS.get(
                field_name,
                field_name,
            )
            for field_name in missing_fields
        ]

        if not labels:
            return (
                "Please provide the required identity "
                "information."
            )

        if len(labels) == 1:
            return (
                f"Please provide the {labels[0]}."
            )

        if len(labels) == 2:
            return (
                "Please provide the following missing "
                f"information: {labels[0]} and "
                f"{labels[1]}."
            )

        joined_labels = (
            ", ".join(labels[:-1])
            + f", and {labels[-1]}"
        )

        return (
            "Please provide the following missing "
            f"information: {joined_labels}."
        )

    @staticmethod
    def _build_mcp_arguments(
        *,
        intent: IntentType,
        metadata: IdentityMetadata,
        request_id: str,
        correlation_id: str,
    ) -> dict[str, Any]:
        """
        Build the MCP tool arguments from validated metadata.
        """

        arguments: dict[str, Any] = {
            "request_id": request_id,
            "correlation_id": correlation_id,
        }

        metadata_values = metadata.model_dump(
            mode="json",
            exclude_none=True,
        )

        arguments.update(
            metadata_values
        )

        if intent is IntentType.GRANT_ACCESS:
            arguments["action"] = "grant"

        elif intent is IntentType.REVOKE_ACCESS:
            arguments["action"] = "revoke"

        return arguments

    def execute(
        self,
        operation: str | IntentType,
        metadata: dict | IdentityMetadata,
        *,
        request_id: str = "untracked",
        correlation_id: str = "untracked",
    ) -> AgentExecutionResult:
        """
        Synchronous compatibility method.

        Existing DemoFlow code can continue calling:

            identity_agent.execute(...)

        FastAPI or other async callers should use execute_async().
        """

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
            "IdentityAgent.execute() cannot be called "
            "inside an active event loop. Use "
            "'await IdentityAgent.execute_async(...)'."
        )

    async def execute_async(
        self,
        operation: str | IntentType,
        metadata: dict | IdentityMetadata,
        *,
        request_id: str = "untracked",
        correlation_id: str = "untracked",
    ) -> AgentExecutionResult:
        """
        Validate and execute an Identity operation through MCP.
        """

        intent = self._normalize_intent(
            operation
        )

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

        logger.info(
            "IDENTITY_AGENT_RECEIVED | "
            "request_id={} | correlation_id={} | "
            "intent={} | username={} | email={} | "
            "employee_number={} | group_name={}",
            request_id,
            correlation_id,
            intent.value,
            validated_metadata.username,
            validated_metadata.email,
            validated_metadata.employee_number,
            validated_metadata.group_name,
        )

        if intent is IntentType.UNKNOWN:
            validation = MetadataValidationResult(
                is_valid=False,
                missing_fields=[],
                derived_fields=[],
                message=(
                    "The requested operation is not "
                    "supported by the Identity Agent."
                ),
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

        (
            validated_metadata,
            derived_fields,
        ) = self._derive_username_from_email(
            validated_metadata
        )

        validation = self._validate_metadata(
            intent=intent,
            metadata=validated_metadata,
            derived_fields=derived_fields,
        )

        if not validation.is_valid:
            clarification_question = (
                self._build_clarification_question(
                    validation.missing_fields
                )
            )

            logger.info(
                "IDENTITY_AGENT_NEEDS_INPUT | "
                "request_id={} | correlation_id={} | "
                "intent={} | missing_fields={} | "
                "derived_fields={} | question={}",
                request_id,
                correlation_id,
                intent.value,
                validation.missing_fields,
                validation.derived_fields,
                clarification_question,
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
                clarification_question=(
                    clarification_question
                ),
                message=clarification_question,
                error=None,
            )

        selected_tool_name = self.TOOL_NAMES.get(
            intent
        )

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
                message=(
                    f"No MCP tool is registered for "
                    f"'{intent.value}'."
                ),
                error="MCP tool not registered",
            )

        mcp_arguments = self._build_mcp_arguments(
            intent=intent,
            metadata=validated_metadata,
            request_id=request_id,
            correlation_id=correlation_id,
        )

        server_module = (
            self.mcp_client.SERVER_MODULES.get(
                intent.value
            )
        )

        mcp_tool_name = (
            self.mcp_client.TOOL_NAMES.get(
                intent.value
            )
        )

        logger.info(
            "MCP_TOOL_DISPATCH | "
            "request_id={} | correlation_id={} | "
            "intent={} | selected_agent=identity_agent | "
            "selected_server={} | mcp_tool={} | "
            "application_tool={}",
            request_id,
            correlation_id,
            intent.value,
            server_module,
            mcp_tool_name,
            selected_tool_name.value,
        )

        try:
            mcp_result = (
                await self.mcp_client.call_tool(
                    operation=intent.value,
                    arguments=mcp_arguments,
                )
            )

            tool_result = ToolResult.model_validate(
                {
                    "success":
                        mcp_result.success,

                    "tool_name":
                        mcp_result.tool_name,

                    "status":
                        mcp_result.status,

                    "operation_id":
                        mcp_result.operation_id,

                    "message":
                        mcp_result.message,

                    "result":
                        mcp_result.result,

                    "error":
                        mcp_result.error,

                    "api_integration_pending":
                        mcp_result.api_integration_pending,
                }
            )

        except Exception as exc:
            logger.exception(
                "MCP_TOOL_EXECUTION_FAILED | "
                "request_id={} | correlation_id={} | "
                "intent={} | selected_server={} | "
                "mcp_tool={} | error_type={}",
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
                message=(
                    "The selected Identity MCP tool "
                    "could not be executed."
                ),
                error=type(exc).__name__,
            )

        logger.info(
            "MCP_TOOL_COMPLETED | "
            "request_id={} | correlation_id={} | "
            "intent={} | selected_server={} | "
            "mcp_tool={} | application_tool={} | "
            "tool_status={} | tool_success={} | "
            "operation_id={}",
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

    def get_supported_operations(
        self,
    ) -> list:
        """
        Return all Identity operations registered through MCP.
        """

        return sorted(
            intent.value
            for intent in self.TOOL_NAMES
        )