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
            from App.tools.identity.get_user_details import GetUserDetailsTool
            
            tool = GetUserDetailsTool()
            result = tool.get_details(user_identifier)
            
            return {
                "success": result.get("success", False),
                "result": result.get("user_data"),
                "message": result.get("message"),
                "error": result.get("error")
            }
            
        except Exception as e:
            logger.error(f"Error in get_user_details: {str(e)}")
            return {
                "success": False,
                "result": None,
                "message": "Failed to retrieve user details",
                "error": str(e)
            }
    
    def _handle_password_reset(self, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle password reset operation.
        """
        logger.info("Processing password reset...")
        
        # Prefer email if the LLM extracted one; it is unambiguous for Graph lookups
        username = metadata.get("email") or metadata.get("username")
        if not username:
            return {
                "success": False,
                "result": None,
                "message": "Username is required for password reset",
                "error": "Missing username in metadata"
            }
        
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
