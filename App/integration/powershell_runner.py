"""Safe, allowlisted PowerShell script execution for TechAdmin tools."""
from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

from loguru import logger
from pydantic import BaseModel, ConfigDict, Field


class ScriptExecutionResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    success: bool
    operation: str
    script_name: str
    exit_code: int | None = None
    duration_seconds: float
    stdout: str = ""
    stderr: str = ""
    error: str | None = None
    dry_run: bool = False


class PowerShellScriptRunner:
    """Executes only approved scripts from the repository Scripts directory."""

    SCRIPT_MAP = {
        "add_user_to_group": "Invoke-AddUserToGroup.ps1",
        "remove_user_from_group": "Invoke-RemoveUserFromGroup.ps1",
        "unlock_user": "Invoke-UnlockUser.ps1",
        "create_group": "Invoke-CreateGroup.ps1",
        "create_user": "Invoke-CreateUser.ps1",
        "delete_user": "Invoke-DeleteUser.ps1",
        "create_vm": "Invoke-CreateVM.ps1",
    }

    DESTRUCTIVE_OPERATIONS = {"delete_user", "remove_user_from_group"}

    def __init__(self, project_root: Path | None = None) -> None:
        self.project_root = project_root or Path(__file__).resolve().parents[2]
        self.scripts_dir = (self.project_root / "Scripts").resolve()
        self.enabled = os.getenv("ENABLE_POWERSHELL_OPERATIONS", "false").lower() == "true"
        self.destructive_enabled = os.getenv("ENABLE_DESTRUCTIVE_OPERATIONS", "false").lower() == "true"
        self.timeout_seconds = int(os.getenv("POWERSHELL_SCRIPT_TIMEOUT", "300"))
        self.executable = shutil.which("pwsh") or shutil.which("powershell.exe") or shutil.which("powershell")

    def execute(
        self,
        operation: str,
        parameters: dict[str, Any],
        *,
        secret_environment: dict[str, str] | None = None,
        approval_granted: bool = False,
    ) -> ScriptExecutionResult:
        started = time.perf_counter()
        script_name = self.SCRIPT_MAP.get(operation)
        if not script_name:
            return self._failure(operation, "", started, "Operation is not allowlisted")
        if not self.enabled:
            return self._failure(operation, script_name, started, "PowerShell operations are disabled. Set ENABLE_POWERSHELL_OPERATIONS=true.", dry_run=True)
        if operation in self.DESTRUCTIVE_OPERATIONS and (not self.destructive_enabled or not approval_granted):
            return self._failure(operation, script_name, started, "Destructive operation requires ENABLE_DESTRUCTIVE_OPERATIONS=true and approval_granted=true.")
        if not self.executable:
            return self._failure(operation, script_name, started, "PowerShell executable was not found")

        script_path = (self.scripts_dir / script_name).resolve()
        if script_path.parent != self.scripts_dir or not script_path.is_file():
            return self._failure(operation, script_name, started, f"Approved script not found: {script_path}")

        command = [self.executable, "-NoLogo", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(script_path)]
        for key, value in parameters.items():
            if value is None or value == "":
                continue
            if not key.replace("_", "").isalnum():
                return self._failure(operation, script_name, started, f"Invalid parameter name: {key}")
            command.extend([f"-{key}", str(value)])

        environment = dict(os.environ)
        for key, value in (secret_environment or {}).items():
            environment[key] = value

        logger.info("SCRIPT_STARTED | operation={} | script={} | parameters={}", operation, script_name, sorted(parameters))
        try:
            completed = subprocess.run(
                command,
                cwd=str(self.project_root),
                env=environment,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self.timeout_seconds,
                shell=False,
                check=False,
            )
            duration = round(time.perf_counter() - started, 3)
            success = completed.returncode == 0
            result = ScriptExecutionResult(
                success=success,
                operation=operation,
                script_name=script_name,
                exit_code=completed.returncode,
                duration_seconds=duration,
                stdout=completed.stdout.strip(),
                stderr=completed.stderr.strip(),
                error=None if success else (completed.stderr.strip() or "PowerShell script failed"),
            )
            logger.info("SCRIPT_COMPLETED | operation={} | script={} | exit_code={} | success={} | duration_seconds={}", operation, script_name, completed.returncode, success, duration)
            return result
        except subprocess.TimeoutExpired:
            return self._failure(operation, script_name, started, f"Script timed out after {self.timeout_seconds} seconds")
        except Exception as exc:
            logger.exception("SCRIPT_FAILED | operation={} | script={} | error_type={}", operation, script_name, type(exc).__name__)
            return self._failure(operation, script_name, started, type(exc).__name__)

    @staticmethod
    def _failure(operation: str, script_name: str, started: float, error: str, dry_run: bool = False) -> ScriptExecutionResult:
        return ScriptExecutionResult(
            success=False,
            operation=operation,
            script_name=script_name,
            duration_seconds=round(time.perf_counter() - started, 3),
            error=error,
            dry_run=dry_run,
        )
