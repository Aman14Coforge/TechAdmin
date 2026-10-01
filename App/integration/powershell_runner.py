"""Allowlisted PowerShell execution for TechAdmin."""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

from loguru import logger
from pydantic import BaseModel, ConfigDict


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
    """
    Execute only PowerShell scripts explicitly registered in SCRIPT_MAP.

    Read-only operations do not require destructive-operation approval.
    Destructive operations require both:
        ENABLE_DESTRUCTIVE_OPERATIONS=true
        approval_granted=true
    """

    SCRIPT_MAP = {
        "reset_password": "Invoke-ResetPassword.ps1",
        "get_user_details": "Invoke-GetUserDetails.ps1",
        "get_computer_details": "Invoke-GetComputerDetails.ps1",
        "unlock_user": "Invoke-UnlockUser.ps1",
        "add_user_to_group": "Invoke-AddUserToGroup.ps1",
        "remove_user_from_group": "Invoke-RemoveUserFromGroup.ps1",
        "create_user": "Invoke-CreateUser.ps1",
        "delete_user": "Invoke-DeleteUser.ps1",
        "create_group": "Invoke-CreateGroup.ps1",
        "create_vm": "Invoke-CreateVM.ps1",
    }

    DESTRUCTIVE_OPERATIONS = {
        "delete_user",
        "remove_user_from_group",
        "reset_password",
    }

    def __init__(
        self,
        project_root: Path | None = None,
    ) -> None:
        self.project_root = (
            project_root
            or Path(__file__).resolve().parents[2]
        ).resolve()

        self.scripts_dir = (
            self.project_root / "Scripts"
        ).resolve()

        self.enabled = (
            os.getenv(
                "ENABLE_POWERSHELL_OPERATIONS",
                "false",
            )
            .strip()
            .casefold()
            in {"true", "1", "yes", "on"}
        )

        self.destructive_enabled = (
            os.getenv(
                "ENABLE_DESTRUCTIVE_OPERATIONS",
                "false",
            )
            .strip()
            .casefold()
            in {"true", "1", "yes", "on"}
        )

        self.timeout = int(
            os.getenv(
                "POWERSHELL_SCRIPT_TIMEOUT",
                "300",
            )
        )

        self.executable = (
            shutil.which("powershell.exe")
            or shutil.which("pwsh")
            or shutil.which("powershell")
        )

        logger.info(
            "POWERSHELL_RUNNER_INITIALIZED | "
            "enabled={} | destructive_enabled={} | "
            "scripts_dir={} | executable={} | "
            "timeout_seconds={} | allowlisted_operations={}",
            self.enabled,
            self.destructive_enabled,
            self.scripts_dir,
            self.executable,
            self.timeout,
            sorted(self.SCRIPT_MAP),
        )

    def execute(
        self,
        operation: str,
        parameters: dict[str, Any],
        *,
        secret_environment: dict[str, str] | None = None,
        approval_granted: bool = False,
    ) -> ScriptExecutionResult:
        start = time.perf_counter()

        normalized_operation = (
            operation.strip().casefold()
            if isinstance(operation, str)
            else ""
        )

        script_name = self.SCRIPT_MAP.get(
            normalized_operation,
            "",
        )

        def fail(
            error: str,
            *,
            dry_run: bool = False,
            exit_code: int | None = None,
            stdout: str = "",
            stderr: str = "",
        ) -> ScriptExecutionResult:
            return ScriptExecutionResult(
                success=False,
                operation=normalized_operation,
                script_name=script_name,
                exit_code=exit_code,
                duration_seconds=round(
                    time.perf_counter() - start,
                    3,
                ),
                stdout=stdout,
                stderr=stderr,
                error=error,
                dry_run=dry_run,
            )

        if not normalized_operation:
            return fail(
                "PowerShell operation name is required."
            )

        if not script_name:
            logger.warning(
                "SCRIPT_OPERATION_REJECTED | "
                "operation={} | reason=not_allowlisted",
                normalized_operation,
            )

            return fail(
                "Operation is not allowlisted."
            )

        if not self.enabled:
            logger.warning(
                "SCRIPT_OPERATION_REJECTED | "
                "operation={} | reason=powershell_disabled",
                normalized_operation,
            )

            return fail(
                "PowerShell operations are disabled.",
                dry_run=True,
            )

        if (
            normalized_operation
            in self.DESTRUCTIVE_OPERATIONS
        ):
            if not self.destructive_enabled:
                logger.warning(
                    "SCRIPT_OPERATION_REJECTED | "
                    "operation={} | "
                    "reason=destructive_operations_disabled",
                    normalized_operation,
                )

                return fail(
                    "Operation requires "
                    "ENABLE_DESTRUCTIVE_OPERATIONS=true."
                )

            if not approval_granted:
                logger.warning(
                    "SCRIPT_OPERATION_REJECTED | "
                    "operation={} | "
                    "reason=approval_not_granted",
                    normalized_operation,
                )

                return fail(
                    "Operation requires "
                    "approval_granted=true."
                )

        if not self.executable:
            return fail(
                "PowerShell executable was not found."
            )

        script_path = (
            self.scripts_dir / script_name
        ).resolve()

        try:
            script_path.relative_to(
                self.scripts_dir
            )
        except ValueError:
            logger.error(
                "SCRIPT_PATH_REJECTED | "
                "operation={} | path={}",
                normalized_operation,
                script_path,
            )

            return fail(
                "Resolved script path is outside "
                "the approved Scripts directory."
            )

        if not script_path.is_file():
            logger.error(
                "SCRIPT_NOT_FOUND | "
                "operation={} | script={}",
                normalized_operation,
                script_path,
            )

            return fail(
                f"Approved script not found: {script_path}"
            )

        safe_parameters = (
            parameters
            if isinstance(parameters, dict)
            else {}
        )

        command = [
            self.executable,
            "-NoLogo",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script_path),
        ]

        for key, value in safe_parameters.items():
            if value is None or value == "":
                continue

            parameter_name = str(key).strip()

            if not parameter_name:
                continue

            if not parameter_name.replace(
                "_",
                "",
            ).isalnum():
                return fail(
                    "Invalid PowerShell parameter name."
                )

            command.extend(
                [
                    f"-{parameter_name}",
                    str(value),
                ]
            )

        environment = dict(os.environ)

        if secret_environment:
            environment.update(
                {
                    str(key): str(value)
                    for key, value
                    in secret_environment.items()
                    if value is not None
                }
            )

        logger.info(
            "SCRIPT_STARTED | "
            "operation={} | script={} | "
            "parameter_names={} | approval_granted={}",
            normalized_operation,
            script_name,
            sorted(safe_parameters),
            approval_granted,
        )

        try:
            completed_process = subprocess.run(
                command,
                cwd=str(self.project_root),
                env=environment,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=self.timeout,
                shell=False,
                check=False,
            )

            stdout = (
                completed_process.stdout.strip()
                if completed_process.stdout
                else ""
            )

            stderr = (
                completed_process.stderr.strip()
                if completed_process.stderr
                else ""
            )

            success = completed_process.returncode == 0

            duration = round(
                time.perf_counter() - start,
                3,
            )

            if success:
                logger.info(
                    "SCRIPT_COMPLETED | "
                    "operation={} | script={} | "
                    "exit_code={} | duration_seconds={}",
                    normalized_operation,
                    script_name,
                    completed_process.returncode,
                    duration,
                )
            else:
                logger.error(
                    "SCRIPT_FAILED | "
                    "operation={} | script={} | "
                    "exit_code={} | duration_seconds={} | "
                    "stderr_present={} | stdout_present={}",
                    normalized_operation,
                    script_name,
                    completed_process.returncode,
                    duration,
                    bool(stderr),
                    bool(stdout),
                )

            return ScriptExecutionResult(
                success=success,
                operation=normalized_operation,
                script_name=script_name,
                exit_code=completed_process.returncode,
                duration_seconds=duration,
                stdout=stdout,
                stderr=stderr,
                error=(
                    None
                    if success
                    else (
                        stderr
                        or stdout
                        or "PowerShell script failed."
                    )
                ),
                dry_run=False,
            )

        except subprocess.TimeoutExpired:
            logger.exception(
                "SCRIPT_TIMEOUT | "
                "operation={} | script={} | "
                "timeout_seconds={}",
                normalized_operation,
                script_name,
                self.timeout,
            )

            return fail(
                (
                    "PowerShell script timed out after "
                    f"{self.timeout} seconds."
                )
            )

        except Exception as exc:
            logger.exception(
                "SCRIPT_EXECUTION_EXCEPTION | "
                "operation={} | script={} | "
                "error_type={}",
                normalized_operation,
                script_name,
                type(exc).__name__,
            )

            return fail(
                type(exc).__name__
            )