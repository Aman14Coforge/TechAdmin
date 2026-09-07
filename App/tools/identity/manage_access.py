"""Grant or revoke AD group membership using approved PowerShell scripts."""
from __future__ import annotations
from loguru import logger
from App.integration.powershell_runner import PowerShellScriptRunner
from App.workflow.state import IntentType, ToolName, ToolRequest, ToolResult, ToolStatus


class AccessManagementTool:
    name = ToolName.MANAGE_ACCESS

    def __init__(self, runner: PowerShellScriptRunner | None = None) -> None:
        self.runner = runner or PowerShellScriptRunner()

    def execute(self, request: ToolRequest) -> ToolResult:
        if request.intent not in {IntentType.GRANT_ACCESS, IntentType.REVOKE_ACCESS}:
            return ToolResult(success=False, tool_name=self.name, status=ToolStatus.REJECTED, message="Unsupported access-management intent.", error="Unsupported intent")
        metadata = request.metadata
        if not metadata.username or not metadata.group_name:
            return ToolResult(success=False, tool_name=self.name, status=ToolStatus.REJECTED, message="Username and group name are required.", error="Missing username or group name")
        grant = request.intent is IntentType.GRANT_ACCESS
        operation = "add_user_to_group" if grant else "remove_user_from_group"
        logger.info("TOOL_CALL | request_id={} | correlation_id={} | tool={} | operation={} | username={} | group_name={}", request.request_id, request.correlation_id, self.name.value, operation, metadata.username, metadata.group_name)
        script = self.runner.execute(
            operation,
            {"UserName": metadata.username, "GroupName": metadata.group_name},
            approval_granted=metadata.approval_granted,
        )
        return ToolResult(
            success=script.success,
            tool_name=self.name,
            status=ToolStatus.COMPLETED if script.success else ToolStatus.FAILED,
            message=script.stdout or (f"Access {'grant' if grant else 'revoke'} completed." if script.success else f"Access {'grant' if grant else 'revoke'} failed."),
            result=script.model_dump(mode="json"),
            error=script.error,
            api_integration_pending=False,
        )
