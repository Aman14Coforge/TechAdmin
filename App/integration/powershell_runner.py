"""Allowlisted PowerShell execution for TechAdmin."""
from __future__ import annotations
import os, shutil, subprocess, time
from pathlib import Path
from typing import Any
from loguru import logger
from pydantic import BaseModel, ConfigDict

class ScriptExecutionResult(BaseModel):
    model_config=ConfigDict(extra="forbid")
    success:bool; operation:str; script_name:str; exit_code:int|None=None; duration_seconds:float; stdout:str=""; stderr:str=""; error:str|None=None; dry_run:bool=False

class PowerShellScriptRunner:
    SCRIPT_MAP={
        "reset_password":"Invoke-ResetPassword.ps1",
        "get_user_details":"Invoke-GetUserDetails.ps1",
        "unlock_user":"Invoke-UnlockUser.ps1",
        "add_user_to_group":"Invoke-AddUserToGroup.ps1",
        "remove_user_from_group":"Invoke-RemoveUserFromGroup.ps1",
        "create_user":"Invoke-CreateUser.ps1",
        "delete_user":"Invoke-DeleteUser.ps1",
        "create_group":"Invoke-CreateGroup.ps1",
        "create_vm":"Invoke-CreateVM.ps1",
    }
    DESTRUCTIVE_OPERATIONS={"delete_user","remove_user_from_group","reset_password"}
    def __init__(self,project_root:Path|None=None)->None:
        self.project_root=project_root or Path(__file__).resolve().parents[2]
        self.scripts_dir=(self.project_root/"Scripts").resolve()
        self.enabled=os.getenv("ENABLE_POWERSHELL_OPERATIONS","false").strip().lower()=="true"
        self.destructive_enabled=os.getenv("ENABLE_DESTRUCTIVE_OPERATIONS","false").strip().lower()=="true"
        self.timeout=int(os.getenv("POWERSHELL_SCRIPT_TIMEOUT","300"))
        self.executable=shutil.which("powershell.exe") or shutil.which("pwsh") or shutil.which("powershell")
    def execute(self,operation:str,parameters:dict[str,Any],*,secret_environment:dict[str,str]|None=None,approval_granted:bool=False)->ScriptExecutionResult:
        start=time.perf_counter(); operation=operation.strip().lower(); script_name=self.SCRIPT_MAP.get(operation,"")
        def fail(error:str,dry:bool=False)->ScriptExecutionResult:
            return ScriptExecutionResult(success=False,operation=operation,script_name=script_name,duration_seconds=round(time.perf_counter()-start,3),error=error,dry_run=dry)
        if not script_name:return fail("Operation is not allowlisted")
        if not self.enabled:return fail("PowerShell operations are disabled",True)
        if operation in self.DESTRUCTIVE_OPERATIONS and (not self.destructive_enabled or not approval_granted):return fail("Operation requires ENABLE_DESTRUCTIVE_OPERATIONS=true and approval_granted=true")
        if not self.executable:return fail("PowerShell executable not found")
        script=(self.scripts_dir/script_name).resolve()
        if script.parent!=self.scripts_dir or not script.is_file():return fail(f"Approved script not found: {script}")
        command=[self.executable,"-NoLogo","-NoProfile","-NonInteractive","-ExecutionPolicy","Bypass","-File",str(script)]
        for key,value in parameters.items():
            if value is not None and value!="":command.extend([f"-{key}",str(value)])
        env=dict(os.environ); env.update(secret_environment or {})
        logger.info("SCRIPT_STARTED | operation={} | script={} | parameter_names={}",operation,script_name,sorted(parameters))
        try:
            cp=subprocess.run(command,cwd=str(self.project_root),env=env,capture_output=True,text=True,encoding="utf-8",errors="replace",timeout=self.timeout,shell=False,check=False)
            success=cp.returncode==0
            return ScriptExecutionResult(success=success,operation=operation,script_name=script_name,exit_code=cp.returncode,duration_seconds=round(time.perf_counter()-start,3),stdout=cp.stdout.strip(),stderr=cp.stderr.strip(),error=None if success else (cp.stderr.strip() or cp.stdout.strip() or "Script failed"))
        except subprocess.TimeoutExpired:return fail(f"Script timed out after {self.timeout} seconds")
        except Exception as exc:return fail(type(exc).__name__)
