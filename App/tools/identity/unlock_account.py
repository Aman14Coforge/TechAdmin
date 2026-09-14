"""Account unlock tool backed by the approved PowerShell script."""
from __future__ import annotations
from loguru import logger
from App.integration.powershell_runner import PowerShellScriptRunner
from App.workflow.state import ToolName, ToolRequest, ToolResult, ToolStatus


class AccountUnlockTool:
    name = ToolName.UNLOCK_ACCOUNT

    def __init__(self, runner: PowerShellScriptRunner | None = None) -> None:
        self.runner = runner or PowerShellScriptRunner()

    def execute(self, request: ToolRequest) -> ToolResult:
        username = request.metadata.username
        if not username:
            return ToolResult(success=False, tool_name=self.name, status=ToolStatus.REJECTED, message="Username is required for account unlock.", error="Missing username")
        logger.info("TOOL_CALL | request_id={} | correlation_id={} | tool={} | username={}", request.request_id, request.correlation_id, self.name.value, username)
        script = self.runner.execute("unlock_user", {"UserName": username})
        return ToolResult(
            success=script.success,
            tool_name=self.name,
            status=ToolStatus.COMPLETED if script.success else ToolStatus.FAILED,
            message=script.stdout or ("Account unlocked successfully." if script.success else "Account unlock failed."),
            result=script.model_dump(mode="json"),
            error=script.error,
            api_integration_pending=False,
        )
