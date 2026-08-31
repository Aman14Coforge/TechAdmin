"""
Get User Details Tool

Purpose:
    Retrieve identity information from Microsoft Graph and return a
    controlled Pydantic ToolResult.
"""

from __future__ import annotations

from typing import Optional

from loguru import logger

from App.integration.microsoft_graph import MicrosoftGraphClient
from App.workflow.state import (
    IntentType,
    ToolName,
    ToolRequest,
    ToolResult,
    ToolStatus,
)


class GetUserDetailsTool:
    """
    Tool for retrieving user information through MicrosoftGraphClient.

    New callers should use execute(ToolRequest).

    get_details(user_identifier) remains available for compatibility.
    """

    name = ToolName.GET_USER_DETAILS

    def __init__(
        self,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        tenant_id: Optional[str] = None,
        graph_client: MicrosoftGraphClient | None = None,
    ) -> None:
        self.graph_client = (
            graph_client
            if graph_client is not None
            else MicrosoftGraphClient(
                client_id=client_id,
                client_secret=client_secret,
                tenant_id=tenant_id,
            )
        )

        logger.info(
            "GetUserDetailsTool initialized"
        )

    def execute(
        self,
        request: ToolRequest,
    ) -> ToolResult:
        """
        Retrieve details for the identity in ToolRequest.
        """

        metadata = request.metadata

        user_identifier = (
            metadata.email
            or metadata.user_id
            or metadata.username
        )

        logger.info(
            "TOOL_CALL | request_id={} | "
            "correlation_id={} | intent={} | "
            "tool={} | username={} | email={} | "
            "user_id={} | employee_number={}",
            request.request_id,
            request.correlation_id,
            request.intent.value,
            self.name.value,
            metadata.username,
            metadata.email,
            metadata.user_id,
            metadata.employee_number,
        )

        if not user_identifier:
            result = ToolResult(
                success=False,
                tool_name=self.name,
                status=ToolStatus.REJECTED,
                message=(
                    "A username, email address or user ID "
                    "is required to retrieve user details."
                ),
                result=None,
                error="Missing user identifier",
                api_integration_pending=False,
            )

            self._log_result(
                request=request,
                result=result,
            )

            return result

        try:
            if not self.graph_client.access_token:
                authenticated = (
                    self.graph_client.authenticate()
                )

                if not authenticated:
                    result = ToolResult(
                        success=False,
                        tool_name=self.name,
                        status=ToolStatus.FAILED,
                        message=(
                            "Microsoft Graph authentication "
                            "failed."
                        ),
                        result=None,
                        error="Graph authentication failed",
                        api_integration_pending=False,
                    )

                    self._log_result(
                        request=request,
                        result=result,
                    )

                    return result

            if "@" in user_identifier:
                user_data = (
                    self.graph_client.get_user_details(
                        user_identifier
                    )
                )
            else:
                user_data = (
                    self.graph_client.find_user_by_username(
                        user_identifier
                    )
                )

            if not user_data:
                result = ToolResult(
                    success=False,
                    tool_name=self.name,
                    status=ToolStatus.FAILED,
                    message=(
                        f"User '{user_identifier}' was not "
                        "found."
                    ),
                    result=None,
                    error="User not found",
                    api_integration_pending=False,
                )

                self._log_result(
                    request=request,
                    result=result,
                )

                return result

            safe_user_data = {
                "id": user_data.get("id"),
                "display_name": user_data.get(
                    "displayName"
                ),
                "user_principal_name": user_data.get(
                    "userPrincipalName"
                ),
                "account_enabled": user_data.get(
                    "accountEnabled"
                ),
                "user_type": user_data.get(
                    "userType"
                ),
                "mail": user_data.get("mail"),
                "on_premises_sync_enabled": (
                    user_data.get(
                        "onPremisesSyncEnabled"
                    )
                ),
            }

            result = ToolResult(
                success=True,
                tool_name=self.name,
                status=ToolStatus.COMPLETED,
                message=(
                    "User details retrieved successfully."
                ),
                result=safe_user_data,
                error=None,
                api_integration_pending=False,
            )

            self._log_result(
                request=request,
                result=result,
            )

            return result

        except Exception as exc:
            logger.exception(
                "TOOL_FAILED | request_id={} | "
                "correlation_id={} | intent={} | "
                "tool={} | error_type={}",
                request.request_id,
                request.correlation_id,
                request.intent.value,
                self.name.value,
                type(exc).__name__,
            )

            return ToolResult(
                success=False,
                tool_name=self.name,
                status=ToolStatus.FAILED,
                message=(
                    "An unexpected error occurred while "
                    "retrieving user details."
                ),
                result=None,
                error=type(exc).__name__,
                api_integration_pending=False,
            )

    def _log_result(
        self,
        *,
        request: ToolRequest,
        result: ToolResult,
    ) -> None:
        logger.info(
            "TOOL_RESULT | request_id={} | "
            "correlation_id={} | intent={} | "
            "tool={} | status={} | success={} | "
            "operation_id={}",
            request.request_id,
            request.correlation_id,
            request.intent.value,
            result.tool_name.value,
            result.status.value,
            result.success,
            result.operation_id,
        )

    def get_details(
        self,
        user_identifier: str,
        fields: Optional[list] = None,
    ) -> dict:
        """
        Backward-compatible method used by existing code.
        """

        metadata = {
            "username": None,
            "email": None,
            "user_id": None,
            "employee_number": None,
        }

        if "@" in user_identifier:
            metadata["email"] = user_identifier
            metadata["username"] = (
                user_identifier.split(
                    "@",
                    maxsplit=1,
                )[0]
            )
            metadata["username_source"] = (
                "derived_from_email"
            )
        else:
            metadata["username"] = user_identifier
            metadata["username_source"] = "explicit"

        request = ToolRequest(
            request_id="legacy_request",
            correlation_id="legacy_correlation",
            intent=IntentType.GET_USER_DETAILS,
            metadata=metadata,
        )

        tool_result = self.execute(
            request
        )

        return {
            "success": tool_result.success,
            "message": tool_result.message,
            "user_data": tool_result.result,
            "error": tool_result.error,
        }