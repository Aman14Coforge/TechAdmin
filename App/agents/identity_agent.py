"""
Identity Agent Module

Purpose:
    Validate Identity operation readiness, derive a username from an
    explicitly supplied email when necessary, ask for missing
    information, select the correct registered tool and execute it.
"""

from __future__ import annotations

import re
from collections.abc import Callable

from loguru import logger

from App.tools.identity.get_user_details import (
    GetUserDetailsTool,
)
from App.tools.identity.investigate_failed_login import (
    FailedLoginInvestigationTool,
)
from App.tools.identity.manage_access import (
    AccessManagementTool,
)
from App.tools.identity.reset_password import (
    GraphAPIPasswordResetTool,
)
from App.tools.identity.unlock_account import (
    AccountUnlockTool,
)
from App.workflow.state import (
    AgentExecutionResult,
    IdentityMetadata,
    IntentType,
    MetadataValidationResult,
    ToolRequest,
    ToolResult,
)


ToolHandler = Callable[
    [ToolRequest],
    ToolResult,
]


class IdentityAgent:
    """
    Identity and Access Management agent.

    Responsibilities:

    1. Normalize and validate the classified intent.
    2. Normalize Pydantic identity metadata.
    3. Derive username from an explicitly supplied email address.
    4. Determine whether mandatory information is present.
    5. Ask for missing information without calling a tool.
    6. Select exactly one tool through a deterministic registry.
    7. Build the Pydantic ToolRequest.
    8. Execute and validate the Pydantic ToolResult.
    9. Log dispatch and execution evidence.
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
        password_reset_tool: (
            GraphAPIPasswordResetTool | None
        ) = None,
        get_user_details_tool: (
            GetUserDetailsTool | None
        ) = None,
        account_unlock_tool: (
            AccountUnlockTool | None
        ) = None,
        access_management_tool: (
            AccessManagementTool | None
        ) = None,
        failed_login_tool: (
            FailedLoginInvestigationTool | None
        ) = None,
    ) -> None:
        password_tool = (
            password_reset_tool
            if password_reset_tool is not None
            else GraphAPIPasswordResetTool()
        )

        details_tool = (
            get_user_details_tool
            if get_user_details_tool is not None
            else GetUserDetailsTool()
        )

        unlock_tool = (
            account_unlock_tool
            if account_unlock_tool is not None
            else AccountUnlockTool()
        )

        access_tool = (
            access_management_tool
            if access_management_tool is not None
            else AccessManagementTool()
        )

        investigation_tool = (
            failed_login_tool
            if failed_login_tool is not None
            else FailedLoginInvestigationTool()
        )

        self.tool_registry: dict[
            IntentType,
            ToolHandler,
        ] = {
            IntentType.PASSWORD_RESET:
                password_tool.execute,

            IntentType.ACCOUNT_UNLOCK:
                unlock_tool.execute,

            IntentType.GRANT_ACCESS:
                access_tool.execute,

            IntentType.REVOKE_ACCESS:
                access_tool.execute,

            IntentType.GET_USER_DETAILS:
                details_tool.execute,

            IntentType.FAILED_LOGIN_INVESTIGATION:
                investigation_tool.execute,
        }

        logger.info(
            "IdentityAgent initialized | "
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
        Derive username from an explicitly provided email address.

        Example:

            Shreesanyog.Rath@Coforge.com

        becomes:

            Shreesanyog.Rath

        No other identity values are inferred.
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
                    "before the selected Identity tool "
                    "can be called."
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
    def _get_tool_name(
        tool_handler: ToolHandler,
    ):
        """
        Read the ToolName from a bound tool execute method.
        """

        tool_instance = getattr(
            tool_handler,
            "__self__",
            None,
        )

        if tool_instance is None:
            return None

        return getattr(
            tool_instance,
            "name",
            None,
        )

    def execute(
        self,
        operation: str | IntentType,
        metadata: dict | IdentityMetadata,
        *,
        request_id: str = "untracked",
        correlation_id: str = "untracked",
    ) -> AgentExecutionResult:
        """
        Validate and execute an Identity operation.
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
            validation = (
                MetadataValidationResult(
                    is_valid=False,
                    missing_fields=[],
                    derived_fields=[],
                    message=(
                        "The requested operation is not "
                        "supported by the Identity Agent."
                    ),
                )
            )

            logger.warning(
                "IDENTITY_AGENT_REJECTED | "
                "request_id={} | correlation_id={} | "
                "reason=unsupported_intent",
                request_id,
                correlation_id,
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

        tool_handler = self.tool_registry.get(
            intent
        )

        if tool_handler is None:
            logger.error(
                "IDENTITY_AGENT_REJECTED | "
                "request_id={} | correlation_id={} | "
                "intent={} | reason=tool_not_registered",
                request_id,
                correlation_id,
                intent.value,
            )

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
                    f"No Identity tool is registered for "
                    f"'{intent.value}'."
                ),
                error="Tool not registered",
            )

        selected_tool_name = self._get_tool_name(
            tool_handler
        )

        if selected_tool_name is None:
            logger.error(
                "IDENTITY_AGENT_REJECTED | "
                "request_id={} | correlation_id={} | "
                "intent={} | "
                "reason=tool_name_unavailable",
                request_id,
                correlation_id,
                intent.value,
            )

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
                    "The configured tool does not expose "
                    "a valid tool name."
                ),
                error="Invalid tool registration",
            )

        tool_request = ToolRequest(
            request_id=request_id,
            correlation_id=correlation_id,
            intent=intent,
            metadata=validated_metadata,
        )

        logger.info(
            "TOOL_DISPATCH | request_id={} | "
            "correlation_id={} | intent={} | "
            "selected_agent=identity_agent | "
            "selected_tool={} | username={} | "
            "username_source={} | email={} | "
            "employee_number={} | group_name={} | "
            "time_window={}",
            request_id,
            correlation_id,
            intent.value,
            selected_tool_name.value,
            validated_metadata.username,
            validated_metadata.username_source,
            validated_metadata.email,
            validated_metadata.employee_number,
            validated_metadata.group_name,
            validated_metadata.time_window,
        )

        try:
            raw_tool_result = tool_handler(
                tool_request
            )

            tool_result = (
                raw_tool_result
                if isinstance(
                    raw_tool_result,
                    ToolResult,
                )
                else ToolResult.model_validate(
                    raw_tool_result
                )
            )

        except Exception as exc:
            logger.exception(
                "TOOL_EXECUTION_FAILED | "
                "request_id={} | correlation_id={} | "
                "intent={} | selected_tool={} | "
                "error_type={}",
                request_id,
                correlation_id,
                intent.value,
                selected_tool_name.value,
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
                    "The selected Identity tool could "
                    "not be executed."
                ),
                error=type(exc).__name__,
            )

        logger.info(
            "IDENTITY_AGENT_COMPLETED | "
            "request_id={} | correlation_id={} | "
            "intent={} | selected_tool={} | "
            "tool_status={} | tool_success={} | "
            "operation_id={}",
            request_id,
            correlation_id,
            intent.value,
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
        Return all Identity operations that have registered tools.
        """

        return sorted(
            intent.value
            for intent in self.tool_registry
        )