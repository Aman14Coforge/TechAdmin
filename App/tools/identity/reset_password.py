"""
Password Reset Tool Module

Purpose:
    Execute password reset operations through the existing
    MicrosoftGraphClient integration.

Compatibility:
    - Existing callers can continue using reset_password(username).
    - Updated Identity Agent code can use execute(ToolRequest).
    - The existing Microsoft Graph integration is not changed.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from loguru import logger

from App.integration.microsoft_graph import MicrosoftGraphClient
from App.workflow.state import (
    IdentityMetadata,
    IntentType,
    ToolName,
    ToolRequest,
    ToolResult,
    ToolStatus,
)


class GraphAPIPasswordResetTool:
    """
    Password-reset tool using the existing Microsoft Graph API client.

    The execute() method is the production tool interface used by the
    Identity Agent.

    The reset_password() method is retained for backward compatibility
    with existing code.
    """

    name = ToolName.RESET_PASSWORD

    def __init__(
        self,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        tenant_id: Optional[str] = None,
        graph_client: Optional[MicrosoftGraphClient] = None,
    ) -> None:
        """
        Initialize the Password Reset Tool.

        Args:
            client_id:
                Azure AD Application ID.

            client_secret:
                Azure AD Application Secret.

            tenant_id:
                Azure Tenant ID.

            graph_client:
                Optional injected MicrosoftGraphClient. This is useful
                for tests and dependency injection.
        """

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
            "GraphAPIPasswordResetTool initialized"
        )

    def execute(
        self,
        request: ToolRequest,
    ) -> ToolResult:
        """
        Execute password reset using a validated Pydantic ToolRequest.

        Resolution order:

        1. Email address
        2. Explicit Graph user ID
        3. Username

        Returns:
            Pydantic ToolResult containing tool execution status.

        Security:
            The temporary password is not logged and is not returned in
            the normal ToolResult payload.
        """

        metadata = request.metadata

        user_identifier = self._get_user_identifier(
            metadata
        )

        logger.info(
            "TOOL_CALL | "
            "request_id={} | "
            "correlation_id={} | "
            "intent={} | "
            "tool={} | "
            "username={} | "
            "username_source={} | "
            "email={} | "
            "user_id={} | "
            "employee_number={}",
            request.request_id,
            request.correlation_id,
            request.intent.value,
            self.name.value,
            metadata.username,
            metadata.username_source,
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
                    "A username, email address, or user ID "
                    "is required for password reset."
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
            authentication_result = (
                self._ensure_authenticated()
            )

            if not authentication_result:
                result = ToolResult(
                    success=False,
                    tool_name=self.name,
                    status=ToolStatus.FAILED,
                    message=(
                        "Failed to authenticate with "
                        "Microsoft Graph API."
                    ),
                    result=None,
                    error="Microsoft Graph authentication failed",
                    api_integration_pending=False,
                )

                self._log_result(
                    request=request,
                    result=result,
                )

                return result

            user_data = self._resolve_user(
                user_identifier
            )

            if not user_data:
                result = ToolResult(
                    success=False,
                    tool_name=self.name,
                    status=ToolStatus.FAILED,
                    message=(
                        f"User '{user_identifier}' was not "
                        "found in Azure AD."
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

            graph_user_id = user_data.get("id")

            user_principal_name = user_data.get(
                "userPrincipalName"
            )

            if not graph_user_id:
                result = ToolResult(
                    success=False,
                    tool_name=self.name,
                    status=ToolStatus.FAILED,
                    message=(
                        "The resolved user does not contain "
                        "a Microsoft Graph user ID."
                    ),
                    result=None,
                    error="Microsoft Graph user ID missing",
                    api_integration_pending=False,
                )

                self._log_result(
                    request=request,
                    result=result,
                )

                return result

            logger.info(
                "PASSWORD_RESET_API_CALL | "
                "request_id={} | "
                "correlation_id={} | "
                "graph_user_id={} | "
                "user_principal_name={}",
                request.request_id,
                request.correlation_id,
                graph_user_id,
                user_principal_name,
            )

            temporary_password = (
                self.graph_client.reset_password(
                    graph_user_id
                )
            )

            if not temporary_password:
                result = ToolResult(
                    success=False,
                    tool_name=self.name,
                    status=ToolStatus.FAILED,
                    message=(
                        "Password reset API call failed."
                    ),
                    result={
                        "user_id": graph_user_id,
                        "user_principal_name":
                            user_principal_name,
                    },
                    error="Password reset API call failed",
                    api_integration_pending=False,
                )

                self._log_result(
                    request=request,
                    result=result,
                )

                return result

            # Do not log or place the temporary password in ToolResult.
            # A separate approved secure delivery process should handle it.
            result = ToolResult(
                success=True,
                tool_name=self.name,
                status=ToolStatus.COMPLETED,
                message=(
                    "Password reset completed successfully. "
                    "A temporary password was generated."
                ),
                result={
                    "user_id": graph_user_id,
                    "user_principal_name":
                        user_principal_name,
                    "temporary_password_generated": True,
                    "temporary_password_redacted": True,
                },
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
                "TOOL_FAILED | "
                "request_id={} | "
                "correlation_id={} | "
                "intent={} | "
                "tool={} | "
                "error_type={}",
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
                    "An unexpected error occurred during "
                    "password reset."
                ),
                result=None,
                error=type(exc).__name__,
                api_integration_pending=False,
            )

    @staticmethod
    def _get_user_identifier(
        metadata: IdentityMetadata,
    ) -> Optional[Any]:
        """
        Return the strongest available identity value.
        """

        return (
            metadata.email
            or metadata.user_id
            or metadata.username
        )

    def _ensure_authenticated(
        self,
    ) -> bool:
        """
        Authenticate only when no access token is available.
        """

        if self.graph_client.access_token:
            return True

        return self.graph_client.authenticate()

    def _resolve_user(
        self,
        user_identifier: str,
    ) -> Optional[Dict[str, Any]]:
        """
        Resolve the user using the existing Microsoft Graph client.

        Email/UPN:
            Direct Microsoft Graph user lookup.

        Username:
            Existing find_user_by_username implementation.
        """

        if "@" in user_identifier:
            return self.graph_client.get_user_details(
                user_identifier
            )

        return self.graph_client.find_user_by_username(
            user_identifier
        )

    @staticmethod
    def _log_result(
        *,
        request: ToolRequest,
        result: ToolResult,
    ) -> None:
        """
        Log only non-secret execution evidence.
        """

        logger.info(
            "TOOL_RESULT | "
            "request_id={} | "
            "correlation_id={} | "
            "intent={} | "
            "tool={} | "
            "status={} | "
            "success={} | "
            "operation_id={} | "
            "temporary_password_redacted=true",
            request.request_id,
            request.correlation_id,
            request.intent.value,
            result.tool_name.value,
            result.status.value,
            result.success,
            result.operation_id,
        )

    def reset_password(
        self,
        username: str,
    ) -> Dict[str, Any]:
        """
        Backward-compatible interface.

        The updated IdentityAgent should use execute(ToolRequest).
        """

        request = ToolRequest(
            request_id="legacy_request",
            correlation_id="legacy_correlation",
            intent=IntentType.PASSWORD_RESET,
            metadata=IdentityMetadata(
                username=username,
                username_source="explicit",
            ),
        )

        result = self.execute(
            request
        )

        return result.model_dump(
            mode="json",
        )

    def validate_username(
        self,
        username: str,
    ) -> tuple[bool, str]:
        """
        Validate that a username or UPN exists in Azure AD.
        """

        if not username:
            return (
                False,
                "Username is required",
            )

        normalized_username = username.strip()

        if len(normalized_username) < 3:
            return (
                False,
                "Invalid username format",
            )

        try:
            if not self._ensure_authenticated():
                return (
                    False,
                    "Microsoft Graph authentication failed",
                )

            user_data = self._resolve_user(
                normalized_username
            )

            if user_data:
                return (
                    True,
                    "Username is valid",
                )

            return (
                False,
                "User not found in Azure AD",
            )

        except Exception as exc:
            logger.exception(
                "USERNAME_VALIDATION_FAILED | "
                "username={} | "
                "error_type={}",
                normalized_username,
                type(exc).__name__,
            )

            return (
                False,
                f"Validation error: "
                f"{type(exc).__name__}",
            )