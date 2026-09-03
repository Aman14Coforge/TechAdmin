"""Get-user-details application tool backed by MicrosoftGraphClient."""
from __future__ import annotations

from typing import Any, Dict, Optional
from loguru import logger

from App.integration.microsoft_graph import MicrosoftGraphClient
from App.workflow.state import IdentityMetadata, IntentType, ToolName, ToolRequest, ToolResult, ToolStatus


class GetUserDetailsTool:
    name = ToolName.GET_USER_DETAILS

    def __init__(
        self,
        client_id: str | None = None,
        client_secret: str | None = None,
        tenant_id: str | None = None,
        graph_client: MicrosoftGraphClient | None = None,
    ) -> None:
        self.graph_client = graph_client or MicrosoftGraphClient(client_id, client_secret, tenant_id)
        logger.info("GetUserDetailsTool initialized")

    def execute(self, request: ToolRequest) -> ToolResult:
        metadata = request.metadata
        identifier = metadata.email or metadata.user_id or metadata.username
        logger.info(
            "TOOL_CALL | request_id={} | correlation_id={} | intent={} | tool={} | username={} | email={} | user_id={} | employee_number={}",
            request.request_id,
            request.correlation_id,
            request.intent.value,
            self.name.value,
            metadata.username,
            metadata.email,
            metadata.user_id,
            metadata.employee_number,
        )
        if not identifier:
            return self._result(request, False, ToolStatus.REJECTED, "A username, email address, or user ID is required.", error="Missing user identifier")
        try:
            if "@" in user_identifier:
                user_data = self.graph_client.get_user_details(user_identifier, fields)
            else:
                user_data = self.graph_client.find_user_by_username(user_identifier)
            
            if not user_data:
                return self._result(request, False, ToolStatus.FAILED, f"User '{identifier}' was not found in Azure AD.", error="User not found")
            safe_data = {
                "id": user_data.get("id"),
                "displayName": user_data.get("displayName"),
                "userPrincipalName": user_data.get("userPrincipalName"),
                "accountEnabled": user_data.get("accountEnabled"),
                "onPremisesSyncEnabled": user_data.get("onPremisesSyncEnabled"),
                "userType": user_data.get("userType"),
                "mail": user_data.get("mail"),
            }
            return self._result(request, True, ToolStatus.COMPLETED, f"User details retrieved successfully for {safe_data.get('userPrincipalName')}.", result=safe_data)
        except Exception as exc:
            logger.exception("GET_USER_DETAILS_TOOL_FAILED | request_id={} | correlation_id={} | error_type={}", request.request_id, request.correlation_id, type(exc).__name__)
            return self._result(request, False, ToolStatus.FAILED, "Error retrieving user details.", error=type(exc).__name__)

    def _result(self, request: ToolRequest, success: bool, status: ToolStatus, message: str, result: dict[str, Any] | None = None, error: str | None = None) -> ToolResult:
        output = ToolResult(success=success, tool_name=self.name, status=status, message=message, result=result, error=error, api_integration_pending=False)
        logger.info("TOOL_RESULT | request_id={} | correlation_id={} | tool={} | status={} | success={} | operation_id={}", request.request_id, request.correlation_id, output.tool_name.value, output.status.value, output.success, output.operation_id)
        return output

    def get_details(self, user_identifier: str, fields: Optional[list] = None) -> Dict[str, Any]:
        request = ToolRequest(
            request_id="legacy_request",
            correlation_id="legacy_correlation",
            intent=IntentType.GET_USER_DETAILS,
            metadata=IdentityMetadata(
                username=user_identifier.split("@", 1)[0] if "@" in user_identifier else user_identifier,
                email=user_identifier if "@" in user_identifier else None,
                username_source="derived_from_email" if "@" in user_identifier else "explicit",
            ),
        )
        result = self.execute(request)
        return {"success": result.success, "message": result.message, "user_data": result.result, "error": result.error}
