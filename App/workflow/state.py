"""
Workflow State Module

Purpose:
    Define Pydantic contracts for workflow state, identity metadata,
    routing decisions, agent results and tool results.
"""

from __future__ import annotations

from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
)


class StrictModel(BaseModel):
    """
    Base Pydantic model for all workflow contracts.
    """

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        validate_assignment=True,
        use_enum_values=False,
    )


class IntentType(str, Enum):
    PASSWORD_RESET = "password_reset"
    ACCOUNT_UNLOCK = "account_unlock"
    GRANT_ACCESS = "grant_access"
    REVOKE_ACCESS = "revoke_access"
    GET_USER_DETAILS = "get_user_details"
    FAILED_LOGIN_INVESTIGATION = (
        "failed_login_investigation"
    )
    UNKNOWN = "unknown"


class AgentType(str, Enum):
    IDENTITY = "identity"
    NETWORK = "network"
    PATCH = "patch"


class WorkflowStatus(str, Enum):
    RECEIVED = "received"
    INTENT_EXTRACTED = "intent_extracted"
    ROUTED = "routed"
    NEEDS_INPUT = "needs_input"
    TOOL_CALLED = "tool_called"
    COMPLETED = "completed"
    UNSUPPORTED = "unsupported"
    FAILED = "failed"


class ToolStatus(str, Enum):
    NOT_IMPLEMENTED = "not_implemented"
    COMPLETED = "completed"
    REJECTED = "rejected"
    FAILED = "failed"


class ToolName(str, Enum):
    RESET_PASSWORD = "reset_password_tool"
    UNLOCK_ACCOUNT = "unlock_account_tool"
    MANAGE_ACCESS = "manage_access_tool"
    GET_USER_DETAILS = "get_user_details_tool"
    INVESTIGATE_FAILED_LOGIN = (
        "investigate_failed_login_tool"
    )


class IdentityMetadata(StrictModel):
    username: str | None = None
    user_id: str | None = None
    email: str | None = None
    employee_number: str | None = None
    group_name: str | None = None
    time_window: str | None = None

    username_source: str | None = None

    @field_validator(
        "username",
        "user_id",
        "email",
        "employee_number",
        "group_name",
        "time_window",
        "username_source",
        mode="before",
    )
    @classmethod
    def normalize_empty_values(
        cls,
        value: Any,
    ) -> Any:
        if not isinstance(value, str):
            return value

        normalized = value.strip()

        if normalized.casefold() in {
            "",
            "null",
            "none",
            "not provided",
            "n/a",
        }:
            return None

        return normalized


class UnifiedExtractionResult(StrictModel):
    success: bool
    intent: IntentType
    confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
    )
    explanation: str
    metadata: IdentityMetadata = Field(
        default_factory=IdentityMetadata,
    )
    error: str | None = None


class MetadataValidationResult(StrictModel):
    is_valid: bool
    missing_fields: list[str] = Field(
        default_factory=list,
    )
    derived_fields: list[str] = Field(
        default_factory=list,
    )
    message: str


class RoutingResult(StrictModel):
    agent_name: str
    agent_type: AgentType
    routing_reason: str


class ToolRequest(StrictModel):
    request_id: str
    correlation_id: str
    intent: IntentType
    metadata: IdentityMetadata


class ToolResult(StrictModel):
    success: bool
    tool_name: ToolName
    status: ToolStatus

    operation_id: str = Field(
        default_factory=lambda: (
            f"op_{uuid4().hex}"
        )
    )

    message: str
    result: dict[str, Any] | None = None
    error: str | None = None
    api_integration_pending: bool = False


class AgentExecutionResult(StrictModel):
    success: bool
    intent: IntentType

    selected_agent: str = "identity_agent"
    selected_tool: ToolName | None = None

    metadata: IdentityMetadata

    validation: MetadataValidationResult

    tool_result: ToolResult | None = None

    clarification_required: bool = False
    clarification_question: str | None = None

    message: str
    error: str | None = None


class WorkflowEvent(StrictModel):
    event: str
    detail: str


class WorkflowState(StrictModel):
    user_input: str = Field(
        min_length=1,
        max_length=4000,
    )

    request_id: str

    correlation_id: str = Field(
        default_factory=lambda: (
            f"corr_{uuid4().hex}"
        )
    )

    intent: IntentType | None = None
    intent_confidence: float = 0.0
    intent_explanation: str | None = None

    metadata: IdentityMetadata = Field(
        default_factory=IdentityMetadata,
    )

    metadata_valid: bool = False

    metadata_validation: (
        MetadataValidationResult | None
    ) = None

    routing_result: RoutingResult | None = None
    agent_type: AgentType | None = None

    execution_result: (
        AgentExecutionResult | None
    ) = None

    execution_success: bool = False

    workflow_status: WorkflowStatus = (
        WorkflowStatus.RECEIVED
    )

    clarification_required: bool = False
    clarification_question: str | None = None

    error_message: str | None = None
    user_response: str | None = None

    events: list[WorkflowEvent] = Field(
        default_factory=list,
    )

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(
            mode="json",
        )