"""
Get User Details Tool for TechAdmin.

Supports:
    - Microsoft Graph API user lookup
    - Active Directory PowerShell user lookup
    - Normalized result structure for the Streamlit UI
    - Manager details
    - Direct, nested, primary, and effective group memberships
    - Safe backend-specific error reporting

Microsoft Graph:
    Uses MicrosoftGraphClient.get_complete_user_details().

PowerShell:
    Uses Invoke-GetUserDetails.ps1 and parses its JSON output.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from loguru import logger

from App.integration.microsoft_graph import MicrosoftGraphClient
from App.workflow.state import (
    AgentExecutionMetadata,
    ExecutionBackend,
    ToolExecutionResult,
)


class GetUserDetailsTool:
    """
    Retrieves a normalized user profile through Microsoft Graph or PowerShell.

    Microsoft Graph provides:
        - Account-enabled status
        - Identity and contact fields
        - Manager
        - Direct group memberships
        - Transitive group memberships

    PowerShell provides:
        - Current Active Directory lockout state
        - Password-expired state
        - Bad-password count
        - Primary group
        - Exact nested-group inheritance paths
    """

    TOOL_NAME = "get_user_details_tool"
    OPERATION_NAME = "get_user_details"

    def __init__(
        self,
        *,
        graph_client: MicrosoftGraphClient | None = None,
        powershell_executor: Any | None = None,
        script_path: str | Path | None = None,
    ) -> None:
        self.graph_client = graph_client or MicrosoftGraphClient()
        self.powershell_executor = powershell_executor

        project_root = Path(__file__).resolve().parents[2]

        self.script_path = Path(
            script_path
            or project_root
            / "Scripts"
            / "Invoke-GetUserDetails.ps1"
        ).resolve()

    def execute(
        self,
        *,
        metadata: AgentExecutionMetadata,
        request_id: str,
        correlation_id: str,
    ) -> ToolExecutionResult:
        """
        Execute Get User Details using the selected backend.

        The metadata object should contain at least one of:
            - email
            - username
            - user_id

        The selected backend should be:
            - ExecutionBackend.API
            - ExecutionBackend.SCRIPT
        """

        operation_id = f"op_{uuid4().hex}"

        user_identifier = self._resolve_user_identifier(
            metadata
        )

        if not user_identifier:
            return self._failure(
                operation_id=operation_id,
                message=(
                    "A user email, username, or user ID is "
                    "required."
                ),
                error="Missing user identifier",
                backend=self._backend_value(
                    metadata.execution_backend
                ),
            )

        backend = metadata.execution_backend

        logger.info(
            "GET_USER_DETAILS_STARTED | "
            "request_id={} | correlation_id={} | "
            "operation_id={} | backend={} | user={}",
            request_id,
            correlation_id,
            operation_id,
            self._backend_value(backend),
            user_identifier,
        )

        if backend == ExecutionBackend.SCRIPT:
            return self._execute_script(
                user_identifier=user_identifier,
                operation_id=operation_id,
                request_id=request_id,
                correlation_id=correlation_id,
            )

        if backend == ExecutionBackend.API:
            return self._execute_graph(
                user_identifier=user_identifier,
                operation_id=operation_id,
                request_id=request_id,
                correlation_id=correlation_id,
            )

        return self._failure(
            operation_id=operation_id,
            message="The selected execution backend is unsupported.",
            error=(
                "Unsupported execution backend: "
                f"{self._backend_value(backend)}"
            ),
            backend=self._backend_value(backend),
        )

    def _execute_graph(
        self,
        *,
        user_identifier: str,
        operation_id: str,
        request_id: str,
        correlation_id: str,
    ) -> ToolExecutionResult:
        """
        Retrieve the complete normalized profile through Microsoft Graph.
        """

        try:
            user = (
                self.graph_client
                .get_complete_user_details(
                    user_identifier
                )
            )

            if not isinstance(user, dict):
                logger.warning(
                    "GET_USER_DETAILS_GRAPH_NOT_FOUND | "
                    "request_id={} | operation_id={} | user={}",
                    request_id,
                    operation_id,
                    user_identifier,
                )

                return self._failure(
                    operation_id=operation_id,
                    message=(
                        "The user could not be retrieved through "
                        "Microsoft Graph."
                    ),
                    error=(
                        "User not found or Microsoft Graph "
                        "request failed."
                    ),
                    backend="api",
                )

            account_enabled = user.get("Enabled")

            logger.info(
                "GET_USER_DETAILS_GRAPH_COMPLETED | "
                "request_id={} | correlation_id={} | "
                "operation_id={} | user={} | "
                "account_enabled={} | direct_groups={} | "
                "nested_groups={}",
                request_id,
                correlation_id,
                operation_id,
                user.get("UserPrincipalName")
                or user_identifier,
                account_enabled,
                user.get(
                    "DirectGroupMembershipCount",
                    0,
                ),
                user.get(
                    "NestedGroupMembershipCount",
                    0,
                ),
            )

            return ToolExecutionResult(
                success=True,
                tool_name=self.TOOL_NAME,
                status="completed",
                operation_id=operation_id,
                message=(
                    "Microsoft Graph user details retrieved "
                    "successfully."
                ),
                result={
                    "backend": "api",
                    "user": user,
                },
                error=None,
                api_integration_pending=False,
            )

        except Exception as exc:
            logger.exception(
                "GET_USER_DETAILS_GRAPH_FAILED | "
                "request_id={} | correlation_id={} | "
                "operation_id={} | user={} | error_type={}",
                request_id,
                correlation_id,
                operation_id,
                user_identifier,
                type(exc).__name__,
            )

            return self._failure(
                operation_id=operation_id,
                message="Microsoft Graph user lookup failed.",
                error=str(exc),
                backend="api",
            )

    def _execute_script(
        self,
        *,
        user_identifier: str,
        operation_id: str,
        request_id: str,
        correlation_id: str,
    ) -> ToolExecutionResult:
        """
        Retrieve the complete profile through Active Directory PowerShell.
        """

        if self.powershell_executor is None:
            return self._failure(
                operation_id=operation_id,
                message=(
                    "The PowerShell executor is not configured."
                ),
                error="PowerShell executor unavailable",
                backend="script",
            )

        if not self.script_path.exists():
            return self._failure(
                operation_id=operation_id,
                message=(
                    "The user-details PowerShell script was "
                    "not found."
                ),
                error=f"Script not found: {self.script_path}",
                backend="script",
            )

        try:
            execution = self._run_powershell(
                user_identifier=user_identifier
            )

            execution_dict = self._execution_to_dict(
                execution
            )

            if not execution_dict.get("success"):
                error = (
                    execution_dict.get("error")
                    or execution_dict.get("stderr")
                    or "PowerShell execution failed."
                )

                logger.error(
                    "GET_USER_DETAILS_SCRIPT_FAILED | "
                    "request_id={} | correlation_id={} | "
                    "operation_id={} | user={} | error={}",
                    request_id,
                    correlation_id,
                    operation_id,
                    user_identifier,
                    error,
                )

                return ToolExecutionResult(
                    success=False,
                    tool_name=self.TOOL_NAME,
                    status="failed",
                    operation_id=operation_id,
                    message="PowerShell user lookup failed.",
                    result={
                        "backend": "script",
                        "user": None,
                        "execution": execution_dict,
                    },
                    error=str(error),
                    api_integration_pending=False,
                )

            stdout = str(
                execution_dict.get("stdout")
                or ""
            ).strip()

            user = self._parse_script_json(
                stdout
            )

            if not isinstance(user, dict):
                return ToolExecutionResult(
                    success=False,
                    tool_name=self.TOOL_NAME,
                    status="failed",
                    operation_id=operation_id,
                    message=(
                        "PowerShell completed without a valid "
                        "user-details result."
                    ),
                    result={
                        "backend": "script",
                        "user": None,
                        "execution": execution_dict,
                    },
                    error="Invalid PowerShell JSON output",
                    api_integration_pending=False,
                )

            if user.get("Success") is not True:
                return ToolExecutionResult(
                    success=False,
                    tool_name=self.TOOL_NAME,
                    status="failed",
                    operation_id=operation_id,
                    message="PowerShell user lookup failed.",
                    result={
                        "backend": "script",
                        "user": None,
                        "execution": execution_dict,
                    },
                    error=str(
                        user.get("Error")
                        or "PowerShell returned an unsuccessful result."
                    ),
                    api_integration_pending=False,
                )

            logger.info(
                "GET_USER_DETAILS_SCRIPT_COMPLETED | "
                "request_id={} | correlation_id={} | "
                "operation_id={} | user={} | direct_groups={} | "
                "nested_groups={}",
                request_id,
                correlation_id,
                operation_id,
                user.get("UserPrincipalName")
                or user_identifier,
                user.get(
                    "DirectGroupMembershipCount",
                    0,
                ),
                user.get(
                    "NestedGroupMembershipCount",
                    0,
                ),
            )

            return ToolExecutionResult(
                success=True,
                tool_name=self.TOOL_NAME,
                status="completed",
                operation_id=operation_id,
                message=(
                    "Active Directory user details retrieved "
                    "successfully."
                ),
                result={
                    "backend": "script",
                    "user": user,
                    "execution": execution_dict,
                },
                error=None,
                api_integration_pending=False,
            )

        except Exception as exc:
            logger.exception(
                "GET_USER_DETAILS_SCRIPT_EXCEPTION | "
                "request_id={} | correlation_id={} | "
                "operation_id={} | user={} | error_type={}",
                request_id,
                correlation_id,
                operation_id,
                user_identifier,
                type(exc).__name__,
            )

            return self._failure(
                operation_id=operation_id,
                message="PowerShell user lookup failed.",
                error=str(exc),
                backend="script",
            )

    def _run_powershell(
        self,
        *,
        user_identifier: str,
    ) -> Any:
        """
        Run the PowerShell script through the project's executor.

        This supports common executor method names without hardcoding
        a user or group.
        """

        parameters = {
            "UserIdentifier": user_identifier,
        }

        if hasattr(
            self.powershell_executor,
            "execute_script",
        ):
            return (
                self.powershell_executor
                .execute_script(
                    script_path=str(self.script_path),
                    parameters=parameters,
                    operation=self.OPERATION_NAME,
                )
            )

        if hasattr(
            self.powershell_executor,
            "run_script",
        ):
            return (
                self.powershell_executor
                .run_script(
                    script_path=str(self.script_path),
                    parameters=parameters,
                    operation=self.OPERATION_NAME,
                )
            )

        if hasattr(
            self.powershell_executor,
            "execute",
        ):
            return self.powershell_executor.execute(
                script_path=str(self.script_path),
                parameters=parameters,
                operation=self.OPERATION_NAME,
            )

        raise RuntimeError(
            "The configured PowerShell executor does not expose "
            "execute_script(), run_script(), or execute()."
        )

    @staticmethod
    def _resolve_user_identifier(
        metadata: AgentExecutionMetadata,
    ) -> str:
        email = getattr(
            metadata,
            "email",
            None,
        )

        if isinstance(email, str) and email.strip():
            return email.strip()

        user_id = getattr(
            metadata,
            "user_id",
            None,
        )

        if isinstance(user_id, str) and user_id.strip():
            return user_id.strip()

        username = getattr(
            metadata,
            "username",
            None,
        )

        if isinstance(username, str) and username.strip():
            return username.strip()

        return ""

    @staticmethod
    def _backend_value(
        backend: ExecutionBackend | None,
    ) -> str:
        if backend is None:
            return "unknown"

        value = getattr(
            backend,
            "value",
            backend,
        )

        return str(value)

    @staticmethod
    def _execution_to_dict(
        execution: Any,
    ) -> dict[str, Any]:
        if isinstance(execution, dict):
            return execution

        if hasattr(execution, "model_dump"):
            dumped = execution.model_dump(
                mode="json"
            )

            if isinstance(dumped, dict):
                return dumped

        if hasattr(execution, "dict"):
            dumped = execution.dict()

            if isinstance(dumped, dict):
                return dumped

        result: dict[str, Any] = {}

        for field_name in (
            "success",
            "operation",
            "script_name",
            "exit_code",
            "duration_seconds",
            "stdout",
            "stderr",
            "error",
            "dry_run",
        ):
            if hasattr(execution, field_name):
                result[field_name] = getattr(
                    execution,
                    field_name,
                )

        return result

    @staticmethod
    def _parse_script_json(
        stdout: str,
    ) -> dict[str, Any] | None:
        """
        Parse the final JSON object written by the PowerShell script.

        Normally stdout contains only compressed JSON. The reversed-line
        fallback protects against an executor adding informational output.
        """

        if not stdout:
            return None

        try:
            parsed = json.loads(stdout)

            return (
                parsed
                if isinstance(parsed, dict)
                else None
            )

        except json.JSONDecodeError:
            pass

        for line in reversed(
            stdout.splitlines()
        ):
            candidate = line.strip()

            if not candidate:
                continue

            if not (
                candidate.startswith("{")
                and candidate.endswith("}")
            ):
                continue

            try:
                parsed = json.loads(candidate)

                if isinstance(parsed, dict):
                    return parsed

            except json.JSONDecodeError:
                continue

        return None

    def _failure(
        self,
        *,
        operation_id: str,
        message: str,
        error: str,
        backend: str,
    ) -> ToolExecutionResult:
        return ToolExecutionResult(
            success=False,
            tool_name=self.TOOL_NAME,
            status="failed",
            operation_id=operation_id,
            message=message,
            result={
                "backend": backend,
                "user": None,
            },
            error=error,
            api_integration_pending=False,
        )