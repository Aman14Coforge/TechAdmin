"""Directory and VM operations backed by approved PowerShell scripts."""
from __future__ import annotations
from loguru import logger
from App.integration.powershell_runner import PowerShellScriptRunner
from App.workflow.state import IntentType, ToolName, ToolRequest, ToolResult, ToolStatus


class DirectoryOperationsTool:
    INTENT_OPERATION = {
        IntentType.CREATE_USER: "create_user",
        IntentType.DELETE_USER: "delete_user",
        IntentType.CREATE_GROUP: "create_group",
        IntentType.CREATE_VM: "create_vm",
    }
    INTENT_TOOL = {
        IntentType.CREATE_USER: ToolName.CREATE_USER,
        IntentType.DELETE_USER: ToolName.DELETE_USER,
        IntentType.CREATE_GROUP: ToolName.CREATE_GROUP,
        IntentType.CREATE_VM: ToolName.CREATE_VM,
    }

    def __init__(self, runner: PowerShellScriptRunner | None = None) -> None:
        self.runner = runner or PowerShellScriptRunner()

    def execute(self, request: ToolRequest) -> ToolResult:
        operation = self.INTENT_OPERATION.get(request.intent)
        tool_name = self.INTENT_TOOL.get(request.intent)
        if not operation or not tool_name:
            return ToolResult(success=False, tool_name=ToolName.DIRECTORY_OPERATION, status=ToolStatus.REJECTED, message="Unsupported directory operation.", error="Unsupported intent")

        data = request.metadata
        parameters: dict[str, object] = {}
        secrets: dict[str, str] = {}
        if request.intent is IntentType.CREATE_USER:
            parameters = {
                "FirstName": data.first_name,
                "LastName": data.last_name,
                "UserName": data.username,
                "EmailAddress": data.email,
                "Department": data.department,
                "TargetOU": data.target_ou,
            }
            if data.initial_password:
                secrets["TECHADMIN_INITIAL_PASSWORD"] = data.initial_password
        elif request.intent is IntentType.DELETE_USER:
            parameters = {"FirstName": data.first_name, "LastName": data.last_name, "UserName": data.username}
        elif request.intent is IntentType.CREATE_GROUP:
            parameters = {"GroupName": data.group_name, "Description": data.description}
        elif request.intent is IntentType.CREATE_VM:
            parameters = {
                "TargetHost": data.target_host,
                "VMName": data.vm_name,
                "CPUCount": data.cpu_count,
                "RAMGB": data.ram_gb,
                "VSwitchName": data.vswitch_name,
                "IPAddress": data.ip_address,
                "Subnet": data.subnet,
                "Gateway": data.gateway,
                "DNS": data.dns,
                "Hostname": data.hostname,
                "Domain": data.domain,
                "DomainUser": data.domain_user,
            }
            if data.domain_password:
                secrets["TECHADMIN_DOMAIN_PASSWORD"] = data.domain_password
            if data.admin_password:
                secrets["TECHADMIN_ADMIN_PASSWORD"] = data.admin_password

        logger.info("TOOL_CALL | request_id={} | correlation_id={} | intent={} | script_operation={}", request.request_id, request.correlation_id, request.intent.value, operation)
        script = self.runner.execute(operation, parameters, secret_environment=secrets, approval_granted=data.approval_granted)
        return ToolResult(
            success=script.success,
            tool_name=tool_name,
            status=ToolStatus.COMPLETED if script.success else ToolStatus.FAILED,
            message=script.stdout or ("Operation completed successfully." if script.success else "Operation failed."),
            result=script.model_dump(mode="json"),
            error=script.error,
            api_integration_pending=False,
        )
