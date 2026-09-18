"""Failed-login investigation tool backed by CrowdStrike."""
from __future__ import annotations
from typing import Any, Protocol
from loguru import logger
from App.integration.crowdstrike_failed_login import CrowdStrikeFailedLoginClient
from App.workflow.state import ToolName, ToolRequest, ToolResult, ToolStatus


class FailedLoginInvestigationClient(Protocol):
    def investigate_failed_login(self, *, username: str, email: str | None, employee_number: str | None, time_window: str | None, correlation_id: str) -> dict[str, Any]: ...


class FailedLoginInvestigationTool:
    name = ToolName.INVESTIGATE_FAILED_LOGIN

    def __init__(self, client: FailedLoginInvestigationClient | None = None) -> None:
        self.client = client or CrowdStrikeFailedLoginClient()
        logger.info("FailedLoginInvestigationTool initialized | client={}", type(self.client).__name__)

    def execute(self, request: ToolRequest) -> ToolResult:
        metadata = request.metadata
        username = metadata.username or (metadata.email.split("@", 1)[0] if metadata.email and "@" in metadata.email else None)
        if not username:
            return self._result(False, ToolStatus.REJECTED, "A username or email is required.", error="Missing user identifier")
        try:
            api_result = self.client.investigate_failed_login(
                username=username,
                email=metadata.email,
                employee_number=metadata.employee_number,
                time_window=metadata.time_window,
                correlation_id=request.correlation_id,
            )
            success = bool(api_result.get("success"))
            return self._result(
                success,
                ToolStatus.COMPLETED if success else ToolStatus.FAILED,
                api_result.get("message") or "Investigation completed.",
                result=api_result.get("result"),
                error=api_result.get("error"),
            )
        except Exception as exc:
            logger.exception("FAILED_LOGIN_TOOL_FAILED | request_id={} | error_type={}", request.request_id, type(exc).__name__)
            return self._result(False, ToolStatus.FAILED, "Failed-login investigation failed.", error=type(exc).__name__)

    def _result(self, success: bool, status: ToolStatus, message: str, *, result: dict[str, Any] | None = None, error: str | None = None) -> ToolResult:
        return ToolResult(
            success=success,
            tool_name=self.name,
            status=status,
            message=message,
            result=result,
            error=error,
            api_integration_pending=False,
        )
