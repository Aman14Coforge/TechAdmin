"""Validated workflow contracts for TechAdmin."""
from __future__ import annotations
from enum import Enum
from typing import Any
from uuid import uuid4
from pydantic import BaseModel, ConfigDict, Field, field_validator

class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, validate_assignment=True)

class IntentType(str, Enum):
    PASSWORD_RESET="password_reset"; ACCOUNT_UNLOCK="account_unlock"; GRANT_ACCESS="grant_access"; REVOKE_ACCESS="revoke_access"; GET_USER_DETAILS="get_user_details"; FAILED_LOGIN_INVESTIGATION="failed_login_investigation"; CREATE_USER="create_user"; DELETE_USER="delete_user"; CREATE_GROUP="create_group"; CREATE_VM="create_vm"; UNKNOWN="unknown"

class ExecutionBackend(str, Enum):
    API="api"; SCRIPT="script"

class AgentType(str, Enum):
    IDENTITY="identity"; NETWORK="network"; PATCH="patch"

class ToolName(str, Enum):
    RESET_PASSWORD="reset_password_tool"; UNLOCK_ACCOUNT="unlock_account_tool"; MANAGE_ACCESS="manage_access_tool"; GET_USER_DETAILS="get_user_details_tool"; INVESTIGATE_FAILED_LOGIN="investigate_failed_login_tool"; CREATE_USER="create_user_tool"; DELETE_USER="delete_user_tool"; CREATE_GROUP="create_group_tool"; CREATE_VM="create_vm_tool"

class ToolStatus(str, Enum):
    NOT_IMPLEMENTED="not_implemented"; COMPLETED="completed"; REJECTED="rejected"; FAILED="failed"

class IdentityMetadata(StrictModel):
    username: str|None=None; user_id: str|None=None; email: str|None=None; employee_number: str|None=None; username_source: str|None=None
    group_name: str|None=None; time_window: str|None=None; execution_backend: ExecutionBackend|None=None
    first_name: str|None=None; last_name: str|None=None; department: str|None=None; target_ou: str|None=None; description: str|None=None
    initial_password: str|None=None; target_host: str|None=None; vm_name: str|None=None; cpu_count: int|None=Field(default=None,ge=1); ram_gb: int|None=Field(default=None,ge=1); vswitch_name: str|None=None
    ip_address: str|None=None; subnet: str|None=None; gateway: str|None=None; dns: str|None=None; hostname: str|None=None; domain: str|None=None; domain_user: str|None=None; domain_password: str|None=None; admin_password: str|None=None; approval_granted: bool=False

    @field_validator("username","user_id","email","employee_number","username_source","group_name","time_window","first_name","last_name","department","target_ou","description","initial_password","target_host","vm_name","vswitch_name","ip_address","subnet","gateway","dns","hostname","domain","domain_user","domain_password","admin_password",mode="before")
    @classmethod
    def blank_to_none(cls,v:Any)->Any:
        if isinstance(v,str):
            v=v.strip()
            return None if v.casefold() in {"","null","none","n/a","not provided"} else v
        return v

class UnifiedExtractionResult(StrictModel):
    success: bool; intent: IntentType; confidence: float=Field(ge=0,le=1); explanation: str; metadata: IdentityMetadata=Field(default_factory=IdentityMetadata); error: str|None=None

class RoutingResult(StrictModel):
    agent_name: str; agent_type: AgentType; routing_reason: str

class MetadataValidationResult(StrictModel):
    is_valid: bool; missing_fields: list[str]=Field(default_factory=list); derived_fields: list[str]=Field(default_factory=list); message: str

class ToolRequest(StrictModel):
    request_id: str; correlation_id: str; intent: IntentType; metadata: IdentityMetadata

class ToolResult(StrictModel):
    success: bool; tool_name: ToolName; status: ToolStatus; operation_id: str=Field(default_factory=lambda:f"op_{uuid4().hex}"); message: str; result: dict[str,Any]|None=None; error: str|None=None; api_integration_pending: bool=False

class AgentExecutionResult(StrictModel):
    success: bool; intent: IntentType; selected_agent: str="identity_agent"; selected_tool: ToolName|None=None; metadata: IdentityMetadata; validation: MetadataValidationResult; tool_result: ToolResult|None=None; clarification_required: bool=False; clarification_question: str|None=None; message: str; error: str|None=None
