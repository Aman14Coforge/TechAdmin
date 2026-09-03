"""Password reset application tool backed by MicrosoftGraphClient."""
from __future__ import annotations

from typing import Any, Dict, Optional
from loguru import logger

from App.integration.microsoft_graph import MicrosoftGraphClient
from App.workflow.state import IdentityMetadata, IntentType, ToolName, ToolRequest, ToolResult, ToolStatus


class GraphAPIPasswordResetTool:
    name = ToolName.RESET_PASSWORD

    def __init__(
        self,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        tenant_id: Optional[str] = None,
        graph_client: MicrosoftGraphClient | None = None,
    ) -> None:
        self.graph_client = graph_client or MicrosoftGraphClient(
            client_id=client_id,
            client_secret=client_secret,
            tenant_id=tenant_id,
        )
        logger.info("GraphAPIPasswordResetTool initialized")

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
            return self._result(request, False, ToolStatus.REJECTED, "A username, email address, or user ID is required for password reset.", error="Missing user identifier")

        try:
            # Find user (handles both bare usernames and full UPNs)
            logger.info(f"Finding user: {username}")
            user_data = self.graph_client.find_user_by_username(username)
            
            if not user_data:
                return self._result(request, False, ToolStatus.FAILED, f"User '{identifier}' was not found in Azure AD.", error="User not found")

            graph_user_id = user_data.get("id")
            if not graph_user_id:
                return self._result(request, False, ToolStatus.FAILED, "Resolved user does not contain a Microsoft Graph user ID.", error="Graph user ID missing")

            temporary_password = self.graph_client.reset_password(graph_user_id)
            if not temporary_password:
                return self._result(
                    request,
                    False,
                    ToolStatus.FAILED,
                    "Password reset API call failed.",
                    result={"user_id": graph_user_id, "user_principal": user_data.get("userPrincipalName")},
                    error="Password reset API call failed",
                )

            # The password is returned only because the existing UI formatter currently expects it.
            # Do not log this value. Remove it when secure out-of-band delivery is implemented.
            return self._result(
                request,
                True,
                ToolStatus.COMPLETED,
                f"Password reset successful for {user_data.get('userPrincipalName')}.",
                result={
                    "user_id": graph_user_id,
                    "user_principal": user_data.get("userPrincipalName"),
                    "new_password": temporary_password,
                },
            )
        except Exception as exc:
            logger.exception("PASSWORD_RESET_TOOL_FAILED | request_id={} | correlation_id={} | error_type={}", request.request_id, request.correlation_id, type(exc).__name__)
            return self._result(request, False, ToolStatus.FAILED, "Error resetting password.", error=type(exc).__name__)

    def _result(
        self,
        request: ToolRequest,
        success: bool,
        status: ToolStatus,
        message: str,
        result: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> ToolResult:
        output = ToolResult(
            success=success,
            tool_name=self.name,
            status=status,
            message=message,
            result=result,
            error=error,
            api_integration_pending=False,
        )
        logger.info(
            "TOOL_RESULT | request_id={} | correlation_id={} | tool={} | status={} | success={} | operation_id={}",
            request.request_id,
            request.correlation_id,
            output.tool_name.value,
            output.status.value,
            output.success,
            output.operation_id,
        )
        return output

    def reset_password(self, username: str) -> Dict[str, Any]:
        request = ToolRequest(
            request_id="legacy_request",
            correlation_id="legacy_correlation",
            intent=IntentType.PASSWORD_RESET,
            metadata=IdentityMetadata(
                username=username if "@" not in username else username.split("@", 1)[0],
                email=username if "@" in username else None,
                username_source="derived_from_email" if "@" in username else "explicit",
            ),
        )
        tool_result = self.execute(request)
        legacy = tool_result.result or {}
        return {
            "success": tool_result.success,
            "message": tool_result.message,
            "user_id": legacy.get("user_id"),
            "user_principal": legacy.get("user_principal"),
            "new_password": legacy.get("new_password"),
            "error": tool_result.error,
        }

    def validate_username(self, username: str) -> tuple[bool, str]:
        if not username or len(username.strip()) < 3:
            return False, "Invalid username format"
        try:
            user_data = self.graph_client.find_user_by_username(username.strip())
            return (True, "Username is valid") if user_data else (False, "User not found in Azure AD")
        except Exception as exc:
            logger.error("Error validating username: {}", type(exc).__name__)
            return False, f"Validation error: {type(exc).__name__}"
