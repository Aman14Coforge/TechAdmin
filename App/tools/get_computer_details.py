"""
Get Computer Details application tool.

Purpose:
    Retrieve one Active Directory computer account by running the approved
    Invoke-GetComputerDetails.ps1 script through PowerShellScriptRunner.

Security:
    - Read-only operation.
    - No destructive-operation approval is required.
    - Does not perform secure-channel repair.
    - Does not modify, enable, disable, move, rename, or delete computers.
"""

from __future__ import annotations

import json
from typing import Any

from loguru import logger

# IMPORTANT:
# Adjust only this import if PowerShellScriptRunner is stored elsewhere.
from App.integration.powershell_runner import (
    PowerShellScriptRunner,
    ScriptExecutionResult,
)

from App.workflow.state import (
    IdentityMetadata,
    ToolName,
    ToolResult,
    ToolStatus,
)


class GetComputerDetailsTool:
    """Retrieve one Active Directory computer through PowerShell."""

    TOOL_NAME = ToolName.GET_COMPUTER_DETAILS
    OPERATION = "get_computer_details"

    def __init__(
        self,
        *,
        powershell_runner: PowerShellScriptRunner | None = None,
    ) -> None:
        self.powershell_runner = (
            powershell_runner
            or PowerShellScriptRunner()
        )

        logger.info(
            "GET_COMPUTER_DETAILS_TOOL_INITIALIZED | "
            "operation={} | tool_name={}",
            self.OPERATION,
            self.TOOL_NAME.value,
        )

    def execute(
        self,
        metadata: IdentityMetadata | dict[str, Any] | None = None,
        *,
        hostname: str | None = None,
        execution_backend: str | None = "script",
        request_id: str = "untracked",
        correlation_id: str = "untracked",
        approval_granted: bool = False,
        **kwargs: Any,
    ) -> ToolResult:
        """
        Execute the read-only Active Directory computer lookup.

        The MCP server may pass either:
            - a validated IdentityMetadata object,
            - a metadata dictionary, or
            - hostname and execution_backend as direct keyword arguments.
        """

        del kwargs

        resolved_metadata = self._build_metadata(
            metadata=metadata,
            hostname=hostname,
            execution_backend=execution_backend,
            approval_granted=approval_granted,
        )

        resolved_hostname = (
            resolved_metadata.hostname.strip()
            if isinstance(
                resolved_metadata.hostname,
                str,
            )
            else ""
        )

        backend = (
            resolved_metadata.execution_backend.value
            if resolved_metadata.execution_backend
            else "script"
        )

        if not resolved_hostname:
            return ToolResult(
                success=False,
                tool_name=self.TOOL_NAME,
                status=ToolStatus.REJECTED,
                message=(
                    "A computer name or hostname is required."
                ),
                result={
                    "backend": "script",
                    "computer": None,
                },
                error="Missing hostname",
                api_integration_pending=False,
            )

        if backend != "script":
            return ToolResult(
                success=False,
                tool_name=self.TOOL_NAME,
                status=ToolStatus.REJECTED,
                message=(
                    "Get Computer Details supports only the "
                    "PowerShell script execution method."
                ),
                result={
                    "backend": "script",
                    "computer": None,
                },
                error="Unsupported execution backend",
                api_integration_pending=False,
            )

        logger.info(
            "GET_COMPUTER_DETAILS_STARTED | "
            "request_id={} | correlation_id={} | "
            "hostname={} | backend={}",
            request_id,
            correlation_id,
            resolved_hostname,
            backend,
        )

        try:
            execution = self.powershell_runner.execute(
                operation=self.OPERATION,
                parameters={
                    "ComputerIdentifier": resolved_hostname,
                    # Directory-only lookup; skip live ping/CIM collection.
                    "IncludeLiveData": "false",
                },
                approval_granted=False,
            )
        except Exception as exc:
            logger.exception(
                "GET_COMPUTER_DETAILS_RUNNER_EXCEPTION | "
                "request_id={} | correlation_id={} | "
                "hostname={} | error_type={}",
                request_id,
                correlation_id,
                resolved_hostname,
                type(exc).__name__,
            )

            return ToolResult(
                success=False,
                tool_name=self.TOOL_NAME,
                status=ToolStatus.FAILED,
                message=(
                    "The Active Directory computer lookup "
                    "could not be started."
                ),
                result={
                    "backend": "script",
                    "computer": None,
                },
                error=f"{type(exc).__name__}: {exc}",
                api_integration_pending=False,
            )

        execution_data = self._execution_to_dict(
            execution
        )

        if not execution.success:
            error_message = (
                execution.error
                or execution.stderr
                or execution.stdout
                or "PowerShell computer lookup failed."
            )

            logger.error(
                "GET_COMPUTER_DETAILS_SCRIPT_FAILED | "
                "request_id={} | correlation_id={} | "
                "hostname={} | exit_code={} | error={}",
                request_id,
                correlation_id,
                resolved_hostname,
                execution.exit_code,
                error_message,
            )

            return ToolResult(
                success=False,
                tool_name=self.TOOL_NAME,
                status=ToolStatus.FAILED,
                message=(
                    "Active Directory computer lookup failed."
                ),
                result={
                    "backend": "script",
                    "computer": None,
                    "execution": execution_data,
                },
                error=str(error_message),
                api_integration_pending=False,
            )

        computer = self._parse_script_output(
            execution.stdout
        )

        if computer is None:
            return ToolResult(
                success=False,
                tool_name=self.TOOL_NAME,
                status=ToolStatus.FAILED,
                message=(
                    "The computer lookup completed but returned "
                    "an invalid JSON response."
                ),
                result={
                    "backend": "script",
                    "computer": None,
                    "execution": execution_data,
                },
                error="Invalid PowerShell JSON response",
                api_integration_pending=False,
            )

        script_success = computer.get(
            "Success",
            computer.get("success"),
        )

        if script_success is not True:
            script_error = (
                computer.get("Error")
                or computer.get("error")
                or "The computer was not found."
            )

            return ToolResult(
                success=False,
                tool_name=self.TOOL_NAME,
                status=ToolStatus.FAILED,
                message=(
                    "Active Directory computer lookup failed."
                ),
                result={
                    "backend": "script",
                    "computer": None,
                    "execution": execution_data,
                },
                error=str(script_error),
                api_integration_pending=False,
            )

        logger.info(
            "GET_COMPUTER_DETAILS_COMPLETED | "
            "request_id={} | correlation_id={} | "
            "hostname={} | computer_name={} | "
            "enabled={} | operating_system={}",
            request_id,
            correlation_id,
            resolved_hostname,
            computer.get("Name"),
            computer.get("Enabled"),
            computer.get("OperatingSystem"),
        )

        return ToolResult(
            success=True,
            tool_name=self.TOOL_NAME,
            status=ToolStatus.COMPLETED,
            message=(
                "Computer details retrieved through "
                "Active Directory PowerShell."
            ),
            result={
                "backend": "script",
                "computer": computer,
                "execution": execution_data,
            },
            error=None,
            api_integration_pending=False,
        )

    @staticmethod
    def _build_metadata(
        *,
        metadata: IdentityMetadata | dict[str, Any] | None,
        hostname: str | None,
        execution_backend: str | None,
        approval_granted: bool,
    ) -> IdentityMetadata:
        if isinstance(metadata, IdentityMetadata):
            updates: dict[str, Any] = {}

            if hostname and not metadata.hostname:
                updates["hostname"] = hostname

            if (
                execution_backend
                and metadata.execution_backend is None
            ):
                updates["execution_backend"] = (
                    execution_backend
                )

            if approval_granted:
                updates["approval_granted"] = True

            if updates:
                return metadata.model_copy(
                    update=updates
                )

            return metadata

        metadata_data = (
            dict(metadata)
            if isinstance(metadata, dict)
            else {}
        )

        if hostname and not metadata_data.get("hostname"):
            metadata_data["hostname"] = hostname

        if (
            execution_backend
            and not metadata_data.get(
                "execution_backend"
            )
        ):
            metadata_data["execution_backend"] = (
                execution_backend
            )

        metadata_data["approval_granted"] = bool(
            metadata_data.get(
                "approval_granted",
                approval_granted,
            )
        )

        return IdentityMetadata.model_validate(
            metadata_data
        )

    @staticmethod
    def _execution_to_dict(
        execution: ScriptExecutionResult,
    ) -> dict[str, Any]:
        if hasattr(execution, "model_dump"):
            data = execution.model_dump(
                mode="json"
            )

            if isinstance(data, dict):
                return data

        return {
            "success": execution.success,
            "operation": execution.operation,
            "script_name": execution.script_name,
            "exit_code": execution.exit_code,
            "duration_seconds": (
                execution.duration_seconds
            ),
            "stdout": execution.stdout,
            "stderr": execution.stderr,
            "error": execution.error,
            "dry_run": execution.dry_run,
        }

    @staticmethod
    def _parse_script_output(
        stdout: str,
    ) -> dict[str, Any] | None:
        """
        Parse the compressed JSON produced by the PowerShell script.

        The normal response contains only JSON. The line fallback protects
        against informational output accidentally written before the payload.
        """

        if not isinstance(stdout, str):
            return None

        cleaned = stdout.strip()

        if not cleaned:
            return None

        try:
            parsed = json.loads(cleaned)

            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass

        for line in reversed(
            cleaned.splitlines()
        ):
            candidate = line.strip()

            if not (
                candidate.startswith("{")
                and candidate.endswith("}")
            ):
                continue

            try:
                parsed = json.loads(candidate)
            except json.JSONDecodeError:
                continue

            if isinstance(parsed, dict):
                return parsed

        return None