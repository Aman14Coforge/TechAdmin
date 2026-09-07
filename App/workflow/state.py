"""
Workflow State Module

Purpose:
    Define validated Pydantic contracts for:

    - Supported TechAdmin intents
    - Agent routing
    - Identity and infrastructure metadata
    - MCP tool requests
    - MCP tool results
    - Identity Agent results
    - Unified LLM extraction results
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
    Base model for TechAdmin workflow contracts.

    extra="forbid" prevents unexpected LLM, MCP, or tool fields from
    silently entering the workflow state.
    """

    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        validate_assignment=True,
        use_enum_values=False,
    )


# ---------------------------------------------------------------------
# Intent and agent enums
# ---------------------------------------------------------------------


class IntentType(str, Enum):
    """
    Every intent supported by the TechAdmin workflow.
    """

    PASSWORD_RESET = "password_reset"
    ACCOUNT_UNLOCK = "account_unlock"
    GRANT_ACCESS = "grant_access"
    REVOKE_ACCESS = "revoke_access"
    GET_USER_DETAILS = "get_user_details"

    FAILED_LOGIN_INVESTIGATION = (
        "failed_login_investigation"
    )

    CREATE_USER = "create_user"
    DELETE_USER = "delete_user"
    CREATE_GROUP = "create_group"
    CREATE_VM = "create_vm"

    UNKNOWN = "unknown"


class AgentType(str, Enum):
    """
    Supported TechAdmin agent families.
    """

    IDENTITY = "identity"
    NETWORK = "network"
    PATCH = "patch"


class ToolName(str, Enum):
    """
    Controlled application-tool names.

    These values identify the business tool behind the MCP tool.
    """

    RESET_PASSWORD = "reset_password_tool"

    UNLOCK_ACCOUNT = "unlock_account_tool"

    MANAGE_ACCESS = "manage_access_tool"

    GET_USER_DETAILS = "get_user_details_tool"

    INVESTIGATE_FAILED_LOGIN = (
        "investigate_failed_login_tool"
    )

    CREATE_USER = "create_user_tool"

    DELETE_USER = "delete_user_tool"

    CREATE_GROUP = "create_group_tool"

    CREATE_VM = "create_vm_tool"

    DIRECTORY_OPERATION = (
        "directory_operation_tool"
    )


class ToolStatus(str, Enum):
    """
    Controlled lifecycle statuses returned by application tools.
    """

    NOT_IMPLEMENTED = "not_implemented"
    COMPLETED = "completed"
    REJECTED = "rejected"
    FAILED = "failed"


class WorkflowStatus(str, Enum):
    """
    Optional overall workflow status.
    """

    RECEIVED = "received"
    INTENT_EXTRACTED = "intent_extracted"
    ROUTED = "routed"
    NEEDS_INPUT = "needs_input"
    TOOL_CALLED = "tool_called"
    COMPLETED = "completed"
    UNSUPPORTED = "unsupported"
    FAILED = "failed"


# ---------------------------------------------------------------------
# Metadata
# ---------------------------------------------------------------------


class IdentityMetadata(StrictModel):
    """
    Metadata used by Identity, Active Directory, access-management, and
    Hyper-V operations.

    Password fields must not be extracted from an LLM response. They
    should be supplied through secure Streamlit password controls.
    """

    # Identity fields
    username: str | None = None
    user_id: str | None = None
    email: str | None = None
    employee_number: str | None = None
    username_source: str | None = None

    # Access-management and investigation fields
    group_name: str | None = None
    time_window: str | None = None

    # User-provisioning and deletion fields
    first_name: str | None = None
    last_name: str | None = None
    department: str | None = None
    target_ou: str | None = None
    initial_password: str | None = None

    # Group-provisioning fields
    description: str | None = None

    # Hyper-V provisioning fields
    target_host: str | None = None
    vm_name: str | None = None
    cpu_count: int | None = Field(
        default=None,
        ge=1,
        le=256,
        description=(
            "Number of virtual CPUs assigned to the VM"
        ),
    )
    ram_gb: int | None = Field(
        default=None,
        ge=1,
        le=4096,
        description=(
            "Virtual-machine memory in gigabytes"
        ),
    )
    vswitch_name: str | None = None

    # VM network fields
    ip_address: str | None = None
    subnet: str | None = None
    gateway: str | None = None
    dns: str | None = None
    hostname: str | None = None

    # Domain-join fields
    domain: str | None = None
    domain_user: str | None = None
    domain_password: str | None = None

    # VM local administrator password
    admin_password: str | None = None

    # Authorization control for destructive operations
    approval_granted: bool = False

    @field_validator(
        "username",
        "user_id",
        "email",
        "employee_number",
        "username_source",
        "group_name",
        "time_window",
        "first_name",
        "last_name",
        "department",
        "target_ou",
        "initial_password",
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
        "domain_password",
        "admin_password",
        mode="before",
    )
    @classmethod
    def blank_to_none(
        cls,
        value: Any,
    ) -> Any:
        """
        Convert blank and null-like strings to None.

        Important:
            Every field named in the decorator above exists directly in
            this model. This fixes the Pydantic decorator-missing-field
            error.
        """

        if value is None:
            return None

        if not isinstance(
            value,
            str,
        ):
            return value

        normalized_value = value.strip()

        if normalized_value.casefold() in {
            "",
            "null",
            "none",
            "n/a",
            "na",
            "not provided",
            "not available",
        }:
            return None

        return normalized_value

    @field_validator(
        "username_source",
        mode="after",
    )
    @classmethod
    def validate_username_source(
        cls,
        value: str | None,
    ) -> str | None:
        """
        Permit only controlled username-source values.
        """

        if value is None:
            return None

        normalized_value = (
            value.strip().casefold()
        )

        if normalized_value not in {
            "explicit",
            "derived_from_email",
        }:
            return None

        return normalized_value


# ---------------------------------------------------------------------
# LLM extraction
# ---------------------------------------------------------------------


class UnifiedExtractionResult(StrictModel):
    """
    Validated result produced by UnifiedIntentMetadataExtractor.
    """

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


# ---------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------


class RoutingResult(StrictModel):
    """
    Validated result returned by AgentRouter.
    """

    agent_name: str

    agent_type: AgentType

    routing_reason: str


# ---------------------------------------------------------------------
# Metadata validation
# ---------------------------------------------------------------------


class MetadataValidationResult(StrictModel):
    """
    Identity Agent metadata-validation outcome.
    """

    is_valid: bool

    missing_fields: list[str] = Field(
        default_factory=list,
    )

    derived_fields: list[str] = Field(
        default_factory=list,
    )

    message: str


# ---------------------------------------------------------------------
# Tool contracts
# ---------------------------------------------------------------------


class ToolRequest(StrictModel):
    """
    Controlled request passed to application tools.

    MCP servers construct this model before calling the existing Python
    application tools.
    """

    request_id: str

    correlation_id: str

    intent: IntentType

    metadata: IdentityMetadata


class ToolResult(StrictModel):
    """
    Controlled result returned by every application tool.
    """

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


# ---------------------------------------------------------------------
# Agent result
# ---------------------------------------------------------------------


class AgentExecutionResult(StrictModel):
    """
    Validated result returned by IdentityAgent.
    """

    success: bool

    intent: IntentType

    selected_agent: str = (
        "identity_agent"
    )

    selected_tool: ToolName | None = None

    metadata: IdentityMetadata

    validation: MetadataValidationResult

    tool_result: ToolResult | None = None

    clarification_required: bool = False

    clarification_question: str | None = None

    message: str

    error: str | None = None


# ---------------------------------------------------------------------
# Optional complete workflow state
# ---------------------------------------------------------------------


class WorkflowEvent(StrictModel):
    """
    Individual workflow audit event.
    """

    event: str

    detail: str


class WorkflowState(StrictModel):
    """
    Complete end-to-end workflow state.

    This model is optional for the current DemoFlow but can be used by
    a future LangGraph implementation.
    """

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

    intent_confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
    )

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

    def to_dict(
        self,
    ) -> dict[str, Any]:
        """
        Convert workflow state to a JSON-compatible dictionary.
        """

        return self.model_dump(
            mode="json",
        )