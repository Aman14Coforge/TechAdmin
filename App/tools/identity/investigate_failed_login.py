"""
Failed Login Investigation Tool

Purpose:
    Investigate repeated login failures or account lockouts through the
    configured investigation API client.
"""

from __future__ import annotations

from typing import Any, Protocol

from loguru import logger

from App.workflow.state import (
    ToolName,
    ToolRequest,
    ToolResult,
    ToolStatus,
)


class FailedLoginInvestigationClient(Protocol):
    """
    Contract expected from the failed-login or lockout investigation
    integration.
    """

    def investigate_failed_login(
        self,
        *,
        username: str,
        email: str | None,
        employee_number: str | None,
        time_window: str | None,
        correlation_id: str,
    ) -> dict[str, Any]:
        ...


class FailedLoginInvestigationTool:
    """
    Tool for investigating failed-login events.

    The API client is injected so the Identity Agent and tool-dispatch
    code do not depend on a particular SIEM, Active Directory, Entra ID,
    or MCP implementation.
    """

    name = ToolName.INVESTIGATE_FAILED_LOGIN

    def __init__(
        self,
        client: (
            FailedLoginInvestigationClient | None
        ) = None,
    ) -> None:
        self.client = client

        logger.info(
            "FailedLoginInvestigationTool initialized | "
            "client_registered={}",
            self.client is not None,
        )

    def execute(
        self,
        request: ToolRequest,
    ) -> ToolResult:
        metadata = request.metadata

        user_identifier = (
            metadata.username
            or metadata.email
            or metadata.user_id
        )

        logger.info(
            "TOOL_CALL | request_id={} | "
            "correlation_id={} | intent={} | "
            "tool={} | username={} | email={} | "
            "employee_number={} | time_window={}",
            request.request_id,
            request.correlation_id,
            request.intent.value,
            self.name.value,
            metadata.username,
            metadata.email,
            metadata.employee_number,
            metadata.time_window,
        )

        if not user_identifier:
            result = ToolResult(
                success=False,
                tool_name=self.name,
                status=ToolStatus.REJECTED,
                message=(
                    "A username, email address or user ID "
                    "is required for failed-login "
                    "investigation."
                ),
                result=None,
                error="Missing user identifier",
                api_integration_pending=(
                    self.client is None
                ),
            )

            self._log_result(
                request=request,
                result=result,
            )

            return result

        if self.client is None:
            result = ToolResult(
                success=False,
                tool_name=self.name,
                status=ToolStatus.NOT_IMPLEMENTED,
                message=(
                    "The failed-login investigation tool "
                    "was called, but its investigation API "
                    "client has not been registered."
                ),
                result={
                    "username": metadata.username,
                    "email": metadata.email,
                    "employee_number": (
                        metadata.employee_number
                    ),
                    "time_window": metadata.time_window,
                },
                error=None,
                api_integration_pending=True,
            )

            self._log_result(
                request=request,
                result=result,
            )

            return result

        try:
            api_result = (
                self.client.investigate_failed_login(
                    username=metadata.username,
                    email=metadata.email,
                    employee_number=(
                        metadata.employee_number
                    ),
                    time_window=metadata.time_window,
                    correlation_id=(
                        request.correlation_id
                    ),
                )
            )

            success = bool(
                api_result.get("success")
            )

            result = ToolResult(
                success=success,
                tool_name=self.name,
                status=(
                    ToolStatus.COMPLETED
                    if success
                    else ToolStatus.FAILED
                ),
                message=api_result.get(
                    "message",
                    (
                        "Failed-login investigation "
                        "completed successfully."
                        if success
                        else (
                            "Failed-login investigation "
                            "failed."
                        )
                    ),
                ),
                result=api_result.get("result"),
                error=api_result.get("error"),
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
                    "An unexpected error occurred during "
                    "failed-login investigation."
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
            "operation_id={} | "
            "api_integration_pending={}",
            request.request_id,
            request.correlation_id,
            request.intent.value,
            result.tool_name.value,
            result.status.value,
            result.success,
            result.operation_id,
            result.api_integration_pending,
        )