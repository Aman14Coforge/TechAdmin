"""Dual-backend identity tools compatible with TechAdmin output guardrails."""
from __future__ import annotations

import json
import re
from typing import Any

from loguru import logger

from App.integration.microsoft_graph import MicrosoftGraphClient
from App.integration.powershell_runner import PowerShellScriptRunner
from App.services.password_vault import password_vault
from App.utils.password_masking import mask_password
from App.workflow.state import (
    ExecutionBackend,
    ToolName,
    ToolRequest,
    ToolResult,
    ToolStatus,
)


NOT_AVAILABLE = "Not Available"

EMAIL_PATTERN = re.compile(
    r"^[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}$",
    re.IGNORECASE,
)

EMPLOYEE_ID_PATTERN = re.compile(
    r"^[A-Z0-9][A-Z0-9._-]{1,31}$",
    re.IGNORECASE,
)

# Description examples supported by these patterns:
#   2828,P
#   2828, P
#   EMP-2828,P
#   Employee ID: 2828,P
#   Employee Code - 2828, P
#   Emp No 2828
#
# The value before the first comma is the employee ID. A trailing comma marker
# such as ",P" is directory metadata and is not part of the employee ID.
DESCRIPTION_EMPLOYEE_PATTERNS = (
    re.compile(
        r"\b(?:employee|emp)\s*"
        r"(?:id|number|no|code)\s*"
        r"(?:is\s*)?[:=#-]?\s*"
        r"(?P<value>[A-Z0-9][A-Z0-9._-]{1,31})"
        r"(?=\s*(?:,|;|$))",
        re.IGNORECASE,
    ),
    re.compile(
        r"^\s*(?P<value>[A-Z0-9][A-Z0-9._-]{1,31})"
        r"\s*(?:,\s*[A-Z0-9._-]+)?\s*$",
        re.IGNORECASE,
    ),
)


def _manager_from_script(
    user: dict[str, Any] | None,
) -> tuple[str, str]:
    if not isinstance(user, dict):
        return NOT_AVAILABLE, NOT_AVAILABLE

    manager_name = user.get("ManagerName") or user.get("ManagerDisplayName")
    manager_email = user.get("ManagerEmail")

    if not manager_name:
        manager_dn = user.get("Manager")
        if isinstance(manager_dn, str) and manager_dn.strip():
            match = re.search(r"CN=([^,]+)", manager_dn, flags=re.IGNORECASE)
            if match:
                manager_name = match.group(1)

    return (
        manager_name or NOT_AVAILABLE,
        manager_email or NOT_AVAILABLE,
    )


def _normalize_email(value: Any) -> str:
    return str(value or "").strip().casefold()


def _normalize_employee_id(value: Any) -> str:
    """Return the canonical employee ID used only for verification.

    Directory descriptions store legacy numeric employee IDs as eight digits,
    for example ``00066878,P``. Operators commonly know that employee as
    ``66878``. Numeric values are therefore left-padded to eight digits before
    comparison. Current eight-digit IDs such as ``81001212`` remain unchanged.
    Non-numeric IDs retain their existing case-insensitive comparison behavior.
    """
    normalized = re.sub(r"\s+", "", str(value or "").strip()).casefold()

    if normalized.isdigit():
        return normalized.zfill(8)

    return normalized


def _extract_employee_id_from_description(description: Any) -> str | None:
    """Extract the employee ID from the AD Description field.

    The Coforge directory format may include a classification marker after a
    comma, for example ``2828,P``. In that format ``2828`` is the employee ID
    and ``P`` is not part of the ID.
    """
    text = str(description or "").strip()
    if not text:
        return None

    for pattern in DESCRIPTION_EMPLOYEE_PATTERNS:
        match = pattern.search(text)
        if not match:
            continue

        value = match.group("value").strip()
        if EMPLOYEE_ID_PATTERN.fullmatch(value):
            return value

    # Defensive fallback for values such as "2828,P,other-data". Only the
    # first comma-delimited token is considered, and it must still pass the
    # strict employee-ID format check.
    first_token = text.split(",", 1)[0].strip()
    first_token = re.sub(
        r"^(?:employee|emp)\s*(?:id|number|no|code)\s*"
        r"(?:is\s*)?[:=#-]?\s*",
        "",
        first_token,
        flags=re.IGNORECASE,
    ).strip()

    if EMPLOYEE_ID_PATTERN.fullmatch(first_token):
        return first_token

    return None


def _parse_script_json(stdout: str) -> dict[str, Any] | None:
    text = str(stdout or "").strip()
    if not text:
        return None

    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        pass

    for line in reversed(text.splitlines()):
        candidate = line.strip()
        if not (candidate.startswith("{") and candidate.endswith("}")):
            continue
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            continue

    return None


class HybridGetUserDetailsTool:
    name = ToolName.GET_USER_DETAILS

    def __init__(self, graph_client=None, runner=None) -> None:
        self.graph = graph_client or MicrosoftGraphClient()
        self.runner = runner or PowerShellScriptRunner()

    def execute(self, request: ToolRequest) -> ToolResult:
        metadata = request.metadata
        identifier = metadata.email or metadata.user_id or metadata.username
        backend = metadata.execution_backend

        if not identifier or backend is None:
            return ToolResult(
                success=False,
                tool_name=self.name,
                status=ToolStatus.REJECTED,
                message="User identifier and execution backend are required.",
                error="Missing identifier or backend",
            )

        if backend == ExecutionBackend.API:
            data = (
                self.graph.get_user_details(identifier)
                if "@" in identifier
                else self.graph.find_user_by_username(identifier)
            )
            if not data:
                return ToolResult(
                    success=False,
                    tool_name=self.name,
                    status=ToolStatus.FAILED,
                    message=f"User '{identifier}' was not found through Microsoft Graph.",
                    error="User not found",
                )

            manager = self.graph.get_manager(data.get("id") or identifier)
            data = dict(data)
            data["manager_name"] = manager.get("manager_name") or NOT_AVAILABLE
            data["manager_email"] = manager.get("manager_email") or NOT_AVAILABLE

            logger.info(
                "USER_LOOKUP_SUCCESS | request_id={} | target_user={} | "
                "backend=api | manager_resolved={}",
                request.request_id,
                data.get("userPrincipalName"),
                data["manager_name"] != NOT_AVAILABLE,
            )

            return ToolResult(
                success=True,
                tool_name=self.name,
                status=ToolStatus.COMPLETED,
                message="User details retrieved through Microsoft Graph API.",
                result={"backend": "api", "user": data},
            )

        execution = self.runner.execute(
            "get_user_details",
            {"UserIdentifier": identifier},
        )

        user: dict[str, Any] | None = None
        if execution.success and execution.stdout:
            user = _parse_script_json(execution.stdout)
            if user is None:
                user = {"raw_output": execution.stdout}

        if isinstance(user, dict):
            manager_name, manager_email = _manager_from_script(user)
            user["manager_name"] = manager_name
            user["manager_email"] = manager_email

        logger.info(
            "USER_LOOKUP_{} | request_id={} | target_user={} | backend=script",
            "SUCCESS" if execution.success else "FAILED",
            request.request_id,
            identifier,
        )

        return ToolResult(
            success=execution.success,
            tool_name=self.name,
            status=ToolStatus.COMPLETED if execution.success else ToolStatus.FAILED,
            message=(
                "User details retrieved through PowerShell."
                if execution.success
                else "PowerShell user lookup failed."
            ),
            result={
                "backend": "script",
                "user": user,
                "execution": execution.model_dump(mode="json"),
            },
            error=execution.error,
        )


class HybridPasswordResetTool:
    name = ToolName.RESET_PASSWORD

    def __init__(self, graph_client=None, runner=None) -> None:
        self.graph = graph_client or MicrosoftGraphClient()
        self.runner = runner or PowerShellScriptRunner()

    def execute(self, request: ToolRequest) -> ToolResult:
        metadata = request.metadata
        email = str(metadata.email or "").strip()
        employee_number = str(metadata.employee_number or "").strip()
        backend = metadata.execution_backend

        if not email:
            return self._rejected(
                "A complete company email address is required for password reset.",
                "Missing email",
            )

        if not EMAIL_PATTERN.fullmatch(email):
            return self._rejected(
                "Enter a valid complete company email address.",
                "Invalid email format",
            )

        if not employee_number:
            return self._rejected(
                "Employee ID is required to verify the user before resetting the password.",
                "Missing employee ID",
            )

        if not EMPLOYEE_ID_PATTERN.fullmatch(employee_number):
            return self._rejected(
                "The employee ID format is invalid.",
                "Invalid employee ID format",
            )

        if backend is None:
            return self._rejected(
                "An execution backend is required.",
                "Missing execution backend",
            )

        if not metadata.approval_granted:
            return self._rejected(
                "Approval is required before resetting the password.",
                "Approval required",
            )

        verification = self._verify_user(
            request=request,
            email=email,
            employee_number=employee_number,
        )

        if not verification["success"]:
            return ToolResult(
                success=False,
                tool_name=self.name,
                status=ToolStatus.REJECTED,
                message=verification["message"],
                result={
                    "backend": backend.value if isinstance(backend, ExecutionBackend) else str(backend),
                    "identity_verified": False,
                    "temporary_password_generated": False,
                },
                error=verification["error"],
            )

        verified_user = verification["user"]
        username = verified_user.get("SamAccountName") or email.split("@", 1)[0]

        if backend == ExecutionBackend.API:
            return self._execute_api_reset(
                request=request,
                email=email,
                verified_user=verified_user,
            )

        if backend == ExecutionBackend.SCRIPT:
            return self._execute_script_reset(
                request=request,
                username=username,
                email=email,
                verified_user=verified_user,
            )

        return self._rejected(
            "The selected execution backend is unsupported.",
            "Unsupported execution backend",
        )

    def _verify_user(
        self,
        *,
        request: ToolRequest,
        email: str,
        employee_number: str,
    ) -> dict[str, Any]:
        logger.info(
            "PASSWORD_RESET_IDENTITY_VERIFICATION_STARTED | request_id={} | target_user={}",
            request.request_id,
            email,
        )

        execution = self.runner.execute(
            "get_user_details",
            {"UserIdentifier": email},
        )

        if not execution.success:
            logger.warning(
                "PASSWORD_RESET_IDENTITY_VERIFICATION_FAILED | request_id={} | "
                "target_user={} | reason=lookup_failed",
                request.request_id,
                email,
            )
            return {
                "success": False,
                "message": (
                    "The employee could not be verified through Active Directory. "
                    "The password was not reset."
                ),
                "error": execution.error or "Get User Details verification failed",
                "user": None,
            }

        user = _parse_script_json(execution.stdout)
        if not isinstance(user, dict):
            return {
                "success": False,
                "message": (
                    "Active Directory returned an invalid verification response. "
                    "The password was not reset."
                ),
                "error": "Invalid Get User Details output",
                "user": None,
            }

        if user.get("Success") is False:
            return {
                "success": False,
                "message": "The employee could not be verified. The password was not reset.",
                "error": str(user.get("Error") or "User lookup failed"),
                "user": None,
            }

        returned_emails = {
            _normalize_email(user.get("UserPrincipalName")),
            _normalize_email(user.get("Mail")),
        }
        returned_emails.discard("")

        submitted_email = _normalize_email(email)
        if submitted_email not in returned_emails:
            logger.warning(
                "PASSWORD_RESET_IDENTITY_VERIFICATION_FAILED | request_id={} | "
                "target_user={} | reason=email_mismatch",
                request.request_id,
                email,
            )
            return {
                "success": False,
                "message": (
                    "The email address does not match the directory record. "
                    "The password was not reset."
                ),
                "error": "Directory email mismatch",
                "user": None,
            }

        description = user.get("Description")
        description_employee_id = _extract_employee_id_from_description(description)

        if not description_employee_id:
            logger.warning(
                "PASSWORD_RESET_IDENTITY_VERIFICATION_FAILED | request_id={} | "
                "target_user={} | reason=employee_id_not_found_in_description | "
                "description_present={}",
                request.request_id,
                email,
                bool(str(description or "").strip()),
            )
            return {
                "success": False,
                "message": (
                    "The employee ID could not be verified from the directory "
                    "Description field. The password was not reset."
                ),
                "error": "Employee ID missing from directory Description",
                "user": None,
            }

        if _normalize_employee_id(description_employee_id) != _normalize_employee_id(employee_number):
            logger.warning(
                "PASSWORD_RESET_IDENTITY_VERIFICATION_FAILED | request_id={} | "
                "target_user={} | reason=employee_id_mismatch",
                request.request_id,
                email,
            )
            return {
                "success": False,
                "message": (
                    "The employee ID does not match the directory record. "
                    "The password was not reset."
                ),
                "error": "Employee ID mismatch",
                "user": None,
            }

        logger.info(
            "PASSWORD_RESET_IDENTITY_VERIFICATION_SUCCESS | request_id={} | target_user={}",
            request.request_id,
            email,
        )

        return {
            "success": True,
            "message": "Employee identity verified.",
            "error": None,
            "user": user,
        }

    def _execute_api_reset(
        self,
        *,
        request: ToolRequest,
        email: str,
        verified_user: dict[str, Any],
    ) -> ToolResult:
        # The existing reset default remains Microsoft Graph API.
        graph_user = self.graph.get_user_details(email)

        if not isinstance(graph_user, dict) or not graph_user.get("id"):
            return ToolResult(
                success=False,
                tool_name=self.name,
                status=ToolStatus.FAILED,
                message=(
                    f"User '{email}' was verified in Active Directory but could not "
                    "be resolved through Microsoft Graph."
                ),
                result={
                    "backend": "api",
                    "identity_verified": True,
                    "temporary_password_generated": False,
                },
                error="Microsoft Graph user not found",
            )

        graph_upn = _normalize_email(graph_user.get("userPrincipalName"))
        graph_mail = _normalize_email(graph_user.get("mail"))
        expected = _normalize_email(email)

        if expected not in {graph_upn, graph_mail}:
            return ToolResult(
                success=False,
                tool_name=self.name,
                status=ToolStatus.REJECTED,
                message=(
                    "The Microsoft Graph account does not match the verified "
                    "Active Directory account. The password was not reset."
                ),
                result={
                    "backend": "api",
                    "identity_verified": True,
                    "temporary_password_generated": False,
                },
                error="Graph identity mismatch",
            )

        password = self.graph.reset_password(graph_user["id"])
        if not password:
            return ToolResult(
                success=False,
                tool_name=self.name,
                status=ToolStatus.FAILED,
                message="Microsoft Graph password reset failed.",
                result={
                    "backend": "api",
                    "identity_verified": True,
                    "temporary_password_generated": False,
                },
                error="Password reset failed",
            )

        manager = self.graph.get_manager(graph_user.get("id") or email)
        script_manager_name, script_manager_email = _manager_from_script(verified_user)

        return self._password_result(
            request=request,
            backend="api",
            username=graph_user.get("userPrincipalName") or email,
            employee_name=(
                graph_user.get("displayName")
                or verified_user.get("DisplayName")
                or email
            ),
            password=password,
            manager_name=manager.get("manager_name") or script_manager_name or NOT_AVAILABLE,
            manager_email=manager.get("manager_email") or script_manager_email or NOT_AVAILABLE,
            message=(
                "Employee identity verified and password reset completed "
                "through Microsoft Graph API."
            ),
        )

    def _execute_script_reset(
        self,
        *,
        request: ToolRequest,
        username: str,
        email: str,
        verified_user: dict[str, Any],
    ) -> ToolResult:
        password = self.graph.generate_temp_password()

        execution = self.runner.execute(
            "reset_password",
            {"UserName": username},
            secret_environment={"TECHADMIN_NEW_PASSWORD": password},
            approval_granted=True,
        )

        if not execution.success:
            logger.warning(
                "PASSWORD_RESET_FAILED | request_id={} | target_user={} | backend=script",
                request.request_id,
                email,
            )
            return ToolResult(
                success=False,
                tool_name=self.name,
                status=ToolStatus.FAILED,
                message="PowerShell password reset failed.",
                result={
                    "backend": "script",
                    "user_name": username,
                    "identity_verified": True,
                    "temporary_password_generated": False,
                    "execution": execution.model_dump(mode="json"),
                },
                error=execution.error,
            )

        reset_output = _parse_script_json(execution.stdout)
        manager_name, manager_email = _manager_from_script(
            reset_output if isinstance(reset_output, dict) else verified_user
        )

        return self._password_result(
            request=request,
            backend="script",
            username=(
                reset_output.get("UserName")
                if isinstance(reset_output, dict)
                else None
            )
            or verified_user.get("UserPrincipalName")
            or username,
            employee_name=(
                reset_output.get("DisplayName")
                if isinstance(reset_output, dict)
                else None
            )
            or verified_user.get("DisplayName")
            or username,
            password=password,
            manager_name=manager_name,
            manager_email=manager_email,
            message=(
                "Employee identity verified and password reset completed "
                "through PowerShell."
            ),
            execution=execution.model_dump(mode="json"),
        )

    def _password_result(
        self,
        *,
        request: ToolRequest,
        backend: str,
        username: str,
        employee_name: str,
        password: str,
        manager_name: str,
        manager_email: str,
        message: str,
        execution: dict[str, Any] | None = None,
    ) -> ToolResult:
        token = password_vault.store(
            password=password,
            username=username,
            employee_name=employee_name,
            manager_name=manager_name,
            manager_email=manager_email,
        )

        logger.info(
            "PASSWORD_RESET_SUCCESS | request_id={} | target_user={} | "
            "backend={} | manager_resolved={}",
            request.request_id,
            username,
            backend,
            manager_name != NOT_AVAILABLE,
        )

        result: dict[str, Any] = {
            "_transient_password": password,
            "backend": backend,
            "identity_verified": True,
            "user_name": username,
            "user_principal_name": username,
            "employee_name": employee_name,
            "temporary_password_generated": True,
            "masked_password": mask_password(password),
            "password_token": token,
            "manager_name": manager_name,
            "manager_email": manager_email,
            "email_sent": False,
            "download_available": True,
        }

        if execution is not None:
            result["execution"] = execution

        return ToolResult(
            success=True,
            tool_name=self.name,
            status=ToolStatus.COMPLETED,
            message=message,
            result=result,
        )

    def _rejected(self, message: str, error: str) -> ToolResult:
        return ToolResult(
            success=False,
            tool_name=self.name,
            status=ToolStatus.REJECTED,
            message=message,
            result={
                "identity_verified": False,
                "temporary_password_generated": False,
            },
            error=error,
        )
