from __future__ import annotations

from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
)


class StrictModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        validate_assignment=True,
        use_enum_values=False,
    )


class Intent(str, Enum):
    PASSWORD_RESET = "password_reset"
    ACCOUNT_UNLOCK = "account_unlock"
    GRANT_ACCESS = "grant_access"
    REVOKE_ACCESS = "revoke_access"
    FAILED_LOGIN_INVESTIGATION = (
        "failed_login_investigation"
    )
    UNKNOWN = "unknown"


class ToolName(str, Enum):
    RESET_PASSWORD = "reset_password_tool"
    UNLOCK_ACCOUNT = "unlock_account_tool"
    GRANT_REVOKE_ACCESS = (
        "grant_revoke_access_tool"
    )
    INVESTIGATE_FAILED_LOGIN = (
        "investigate_failed_login_tool"
    )


class ToolStatus(str, Enum):
    NOT_IMPLEMENTED = "not_implemented"
    SKIPPED = "skipped"
    FAILED = "failed"


class WorkflowStatus(str, Enum):
    RECEIVED = "received"
    NEEDS_INPUT = "needs_input"
    READY_FOR_TOOL = "ready_for_tool"
    TOOL_CALLED = "tool_called"
    UNSUPPORTED = "unsupported"
    FAILED = "failed"


class ExtractedFields(StrictModel):
    username: str | None = None
    email: str | None = None
    employee_id: str | None = None
    group_name: str | None = None
    time_window: str | None = None

    username_source: str | None = None

    @field_validator(
        "username",
        "email",
        "employee_id",
        "group_name",
        "time_window",
        "username_source",
        mode="before",
    )
    @classmethod
    def blank_to_none(
        cls,
        value: Any,
    ) -> Any:
        if (
            isinstance(value, str)
            and not value.strip()
        ):
            return None

        return value


class LLMExtraction(StrictModel):
    intent: Intent

    username: str | None = None
    email: str | None = None
    employee_id: str | None = None
    group_name: str | None = None
    time_window: str | None = None

    confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
    )


class ValidationResult(StrictModel):
    is_valid: bool = False

    missing_fields: list[str] = Field(
        default_factory=list,
    )

    rejected_fields: list[str] = Field(
        default_factory=list,
    )

    derived_fields: list[str] = Field(
        default_factory=list,
    )

    reason: str | None = None


class ToolRequest(StrictModel):
    correlation_id: UUID
    intent: Intent
    fields: ExtractedFields


class ToolResult(StrictModel):
    tool: ToolName
    status: ToolStatus
    message: str

    api_integration_pending: bool = True

    operation_id: UUID = Field(
        default_factory=uuid4,
    )


class AuditEvent(StrictModel):
    event: str
    detail: str


class WorkflowState(StrictModel):
    user_query: str = Field(
        min_length=1,
        max_length=4000,
    )

    correlation_id: UUID = Field(
        default_factory=uuid4,
    )

    intent: Intent | None = None
    confidence: float | None = None

    fields: ExtractedFields = Field(
        default_factory=ExtractedFields,
    )

    validation: ValidationResult | None = None

    workflow_status: WorkflowStatus = (
        WorkflowStatus.RECEIVED
    )

    selected_agent: str | None = None

    tool_called: ToolName | None = None
    tool_result: ToolResult | None = None

    clarification_required: bool = False
    clarification_question: str | None = None

    events: list[AuditEvent] = Field(
        default_factory=list,
    )

    error: str | None = None


class IntentMappingEntry(StrictModel):
    agent: str
    tool: str


class AppSettings(StrictModel):
    name: str
    environment: str
    log_level: str


class LLMYamlSettings(StrictModel):
    provider: str
    model_name: str
    temperature: float = 0
    top_p: float = 0.9
  