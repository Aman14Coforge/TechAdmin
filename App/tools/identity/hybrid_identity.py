"""Dual-backend password reset and user-details tools."""
from __future__ import annotations
from typing import Any
from App.integration.microsoft_graph import MicrosoftGraphClient
from App.integration.powershell_runner import PowerShellScriptRunner
from App.workflow.state import ExecutionBackend, ToolName, ToolRequest, ToolResult, ToolStatus

class HybridGetUserDetailsTool:
    name=ToolName.GET_USER_DETAILS
    def __init__(self,graph_client:MicrosoftGraphClient|None=None,runner:PowerShellScriptRunner|None=None)->None:
        self.graph=graph_client or MicrosoftGraphClient(); self.runner=runner or PowerShellScriptRunner()
    def execute(self,request:ToolRequest)->ToolResult:
        m=request.metadata; identifier=m.email or m.user_id or m.username; backend=m.execution_backend
        if not identifier or backend is None:return ToolResult(success=False,tool_name=self.name,status=ToolStatus.REJECTED,message="User identifier and execution backend are required.",error="Missing identifier or backend")
        if backend is ExecutionBackend.API:
            data=self.graph.get_user_details(identifier) if "@" in identifier else self.graph.find_user_by_username(identifier)
            if not data:return ToolResult(success=False,tool_name=self.name,status=ToolStatus.FAILED,message=f"User '{identifier}' was not found through Microsoft Graph.",error="User not found")
            safe={k:data.get(k) for k in ("id","displayName","userPrincipalName","accountEnabled","onPremisesSyncEnabled","userType","mail")}
            return ToolResult(success=True,tool_name=self.name,status=ToolStatus.COMPLETED,message="User details retrieved through Microsoft Graph API.",result={"backend":"api","user":safe})
        script=self.runner.execute("get_user_details",{"UserIdentifier":identifier})
        return ToolResult(success=script.success,tool_name=self.name,status=ToolStatus.COMPLETED if script.success else ToolStatus.FAILED,message=script.stdout or "PowerShell user lookup failed.",result={"backend":"script","execution":script.model_dump(mode="json")},error=script.error)

class HybridPasswordResetTool:
    name=ToolName.RESET_PASSWORD
    def __init__(self,graph_client:MicrosoftGraphClient|None=None,runner:PowerShellScriptRunner|None=None)->None:
        self.graph=graph_client or MicrosoftGraphClient(); self.runner=runner or PowerShellScriptRunner()
    def execute(self,request:ToolRequest)->ToolResult:
        m=request.metadata; identifier=m.email or m.user_id or m.username; backend=m.execution_backend
        if not identifier or backend is None:return ToolResult(success=False,tool_name=self.name,status=ToolStatus.REJECTED,message="User identifier and execution backend are required.",error="Missing identifier or backend")
        user=self.graph.get_user_details(identifier) if "@" in identifier else self.graph.find_user_by_username(identifier)
        if backend is ExecutionBackend.API:
            if not user or not user.get("id"):return ToolResult(success=False,tool_name=self.name,status=ToolStatus.FAILED,message=f"User '{identifier}' was not found through Microsoft Graph.",error="User not found")
            temporary=self.graph.reset_password(user["id"])
            if not temporary:return ToolResult(success=False,tool_name=self.name,status=ToolStatus.FAILED,message="Microsoft Graph password reset failed.",error="Password reset failed")
            return ToolResult(success=True,tool_name=self.name,status=ToolStatus.COMPLETED,message="Password reset completed through Microsoft Graph API. Temporary password generated and redacted.",result={"backend":"api","user_principal_name":user.get("userPrincipalName"),"temporary_password_generated":True,"temporary_password_redacted":True})
        # Generate inside trusted Python code. Never put the password in chat or command arguments.
        temporary=self.graph.generate_temp_password()
        script=self.runner.execute("reset_password",{"UserName":m.username or identifier},secret_environment={"TECHADMIN_NEW_PASSWORD":temporary},approval_granted=m.approval_granted)
        return ToolResult(success=script.success,tool_name=self.name,status=ToolStatus.COMPLETED if script.success else ToolStatus.FAILED,message=(script.stdout+" Temporary password generated and redacted.") if script.success else "PowerShell password reset failed.",result={"backend":"script","temporary_password_generated":script.success,"temporary_password_redacted":True,"execution":script.model_dump(mode="json")},error=script.error)
