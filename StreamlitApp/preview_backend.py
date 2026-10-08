"""Preview backend for the TechAdmin UI.

Enabled only when ``TECHADMIN_UI_PREVIEW=true``. It mirrors the public surface
of ``flow_service`` (and the two App.db helpers app.py uses) with in-memory
sample data, so the interface can be designed, demoed and tested without
Ollama, Microsoft Graph, PowerShell or PostgreSQL.

Nothing in this module talks to a real directory. Never enable preview mode on
a shared or production deployment: it also relaxes the sign-in check.
"""
from __future__ import annotations

import re
import secrets
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict

LOG_FILE = Path("logs") / "techadmin-preview.log"

_DIRECTORY: dict[str, dict[str, Any]] = {
    "amit.bhagat@coforge.com": {
        "Name": "Amit Pradeep Bhagat",
        "DisplayName": "Amit Pradeep Bhagat",
        "SamAccountName": "Amit.Bhagat",
        "UserPrincipalName": "Amit.Bhagat@Coforge.com",
        "Mail": "amit.bhagat@coforge.com",
        "Department": "Data & Analytics",
        "JobTitle": "Senior Data Engineer",
        "ManagerName": "Aman Gupta",
        "ManagerEmail": "aman.gupta@coforge.com",
        "Enabled": True,
        "LockedOut": True,
        "BadPasswordCount": 5,
        "PasswordExpired": False,
        "PasswordNeverExpires": False,
        "PasswordLastSet": "2026-08-21T09:14:00Z",
        "MfaStatus": "Enforced",
        "PrimaryGroupName": "Domain Users",
        "DirectGroups": [
            {"Name": "Project_VPN_Group", "GroupCategory": "Security", "GroupScope": "Universal"},
            {"Name": "Block-Personal-Mail-Resign", "GroupCategory": "Security", "GroupScope": "Universal"},
        ],
        "NestedGroups": [],
    },
    "migrationtest2@coforge.com": {
        "Name": "Migration Test 2",
        "DisplayName": "Migration Test 2",
        "SamAccountName": "MigrationTest2",
        "UserPrincipalName": "MigrationTest2@Coforge.com",
        "Mail": "migrationtest2@coforge.com",
        "Department": "IT Operations",
        "ManagerName": "Aman Gupta",
        "ManagerEmail": "aman.gupta@coforge.com",
        "Enabled": True,
        "LockedOut": False,
        "PasswordExpired": False,
        "PasswordNeverExpires": False,
        "MfaStatus": "Enforced",
        "PrimaryGroupName": "Domain Users",
        "DirectGroups": [
            {"Name": "TechAI_Group", "GroupCategory": "Security", "GroupScope": "Global"},
        ],
        "NestedGroups": [
            {"Name": "All_Staff_Distribution", "GroupCategory": "Distribution", "GroupScope": "Universal",
             "NestingLevel": 1, "InheritedFrom": "TechAI_Group"},
        ],
    },
    "migrationtest3@coforge.com": {
        "Name": "Migration Test 3",
        "DisplayName": "Migration Test 3",
        "SamAccountName": "MigrationTest3",
        "UserPrincipalName": "MigrationTest3@Coforge.com",
        "Mail": "migrationtest3@coforge.com",
        "Department": "IT Operations",
        "Enabled": False,
        "LockedOut": False,
        "PasswordExpired": True,
        "PasswordNeverExpires": False,
        "PrimaryGroupName": "Domain Users",
        "DirectGroups": [],
        "NestedGroups": [],
    },
}

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


@dataclass
class _VaultEntry:
    username: str
    employee_name: str
    password: str
    manager_name: str
    manager_email: str


_VAULT: dict[str, _VaultEntry] = {}
_HISTORY: list[dict[str, Any]] = []


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _seed_history() -> None:
    if _HISTORY:
        return
    base = _now()
    _HISTORY.extend([
        {"request_id": "seed-1", "request": "Account lockout check", "operation": "failed_login_investigation",
         "target": "migrationtest3@coforge.com", "status": "completed", "requested_at": base - timedelta(days=1, hours=2)},
        {"request_id": "seed-2", "request": "Reset password", "operation": "password_reset",
         "target": "migrationtest2@coforge.com", "status": "completed", "requested_at": base - timedelta(hours=1, minutes=3)},
    ])


def _intent_for(text: str) -> str | None:
    t = text.casefold()
    if re.search(r"\b(reset|change)\b.*\bpassword\b|\bpassword\b.*\breset\b", t):
        return "password_reset"
    if "unlock" in t:
        return "account_unlock"
    if re.search(r"\b(failed|lockout|sign-?ins?|logins?|log-?ons?)\b", t) and re.search(r"investigat|check|why|analy", t):
        return "failed_login_investigation"
    if re.search(r"\badd\b.*\bgroup\b", t):
        return "add_user_to_group"
    if re.search(r"\bremove\b.*\bgroup\b", t):
        return "remove_user_from_group"
    if re.search(r"detail|look ?up|profile|who is|show|get user|group membership", t):
        return "get_user_details"
    return None


def _base(query: str, request_id: str, correlation_id: str, intent: str | None, email: str | None) -> Dict[str, Any]:
    return {
        "success": True,
        "request_id": request_id,
        "correlation_id": correlation_id,
        "user_input": query,
        "intent": intent,
        "confidence": 0.95 if intent else 0.3,
        "metadata": {"email": email, "username": email.split("@")[0] if email else None},
        "selected_agent": "identity_agent (preview)",
        "tool_result": None,
        "clarification_required": False,
        "clarification_question": None,
        "confirmation_required": False,
        "confirmation_prompt": None,
        "message": None,
        "error": None,
    }


def _sample_report(email: str) -> dict[str, Any]:
    now = _now()
    events = []
    for i, (eid, name, code, ip, ws) in enumerate([
        (4771, "Kerberos pre-authentication failed", "0x18", "10.42.8.17", "CFG-LT-2231"),
        (4771, "Kerberos pre-authentication failed", "0x18", "10.42.8.17", "CFG-LT-2231"),
        (4625, "An account failed to log on", "0xc000006a", "10.42.8.17", "CFG-LT-2231"),
        (4771, "Kerberos pre-authentication failed", "0x18", "10.42.12.90", "CFG-VDI-118"),
        (4740, "A user account was locked out", None, None, "CFG-LT-2231"),
    ]):
        events.append({
            "timestamp": (now - timedelta(minutes=55 - i * 9)).isoformat(),
            "event_id": eid, "event_name": name, "failure_code": code,
            "source_ip": ip, "workstation": ws, "service_name": "krbtgt" if eid == 4771 else None,
        })
    return {
        "target_user": email,
        "requested_time_window": "last 24 hours",
        "generated_at_utc": now.isoformat(),
        "timeline": events,
        "event_counts": {"4625": 1, "4740": 1, "4771": 3},
        "total_matching_events": len(events),
        "lockout_detected": True,
        "effective_start_utc": (now - timedelta(hours=24)).isoformat(),
        "effective_end_utc": now.isoformat(),
        "first_event_utc": events[0]["timestamp"],
        "last_event_utc": events[-1]["timestamp"],
        "diagnostics": {"raw_events_returned": 9, "valid_account_events": 6, "events_outside_requested_window": 0,
                        "excluded_source_events": 1, "duplicate_events_removed": 0, "matching_events": len(events)},
    }


class PreviewFlowService:
    """Same run_query contract as flow_service.FlowService, backed by sample data."""

    def run_query(self, user_query: str, *, confirmed: bool = False, request_id: str | None = None,
                  correlation_id: str | None = None, requester_id: str | None = None) -> Dict[str, Any]:
        del requester_id
        time.sleep(0.9)  # make the working state visible
        query = (user_query or "").strip()
        request_id = request_id or f"ui_{uuid.uuid4().hex[:8]}"
        correlation_id = correlation_id or f"corr_{uuid.uuid4().hex}"
        email_match = _EMAIL_RE.search(query)
        email = email_match.group(0).casefold() if email_match else None
        intent = _intent_for(query)
        response = _base(query, request_id, correlation_id, intent, email)

        if not intent:
            response.update(success=False, message=(
                "I can look up users, reset passwords, unlock accounts, change group membership, "
                "or investigate failed sign-ins. What would you like to do?"), error="unknown_intent")
            return response
        if not email:
            response.update(clarification_required=True, success=False,
                            clarification_question="Which user should I run this for? Please give their work email address.")
            return response

        user = _DIRECTORY.get(email)
        if user is None:
            response.update(success=False, error="user_not_found",
                            message=f"No directory profile matched {email}.",
                            tool_result={"success": False, "message": f"User not found: {email}", "result": None})
            self._record(query, intent, email, "failed")
            return response

        needs_approval = intent in {"password_reset", "account_unlock", "add_user_to_group", "remove_user_from_group"}
        if needs_approval and not confirmed:
            verb = {"password_reset": "reset the password for", "account_unlock": "unlock the account of",
                    "add_user_to_group": "add a group membership for",
                    "remove_user_from_group": "remove a group membership for"}[intent]
            response.update(success=None, confirmation_required=True, guardrail_action="require_confirmation",
                            confirmation_prompt=(f"This will {verb} {user['DisplayName']} ({user['UserPrincipalName']}). "
                                                 "The change is applied to the live directory and recorded in the audit log."))
            self._record(query, intent, email, "awaiting_approval", request_id)
            return response

        if intent == "get_user_details":
            result = {"backend": "script", "user": dict(user)}
            msg = "User details retrieved successfully."
        elif intent == "password_reset":
            token = secrets.token_urlsafe(16)
            pwd = "Pv-" + secrets.token_urlsafe(9)
            _VAULT[token] = _VaultEntry(user["UserPrincipalName"], user["DisplayName"], pwd,
                                        user.get("ManagerName") or "", user.get("ManagerEmail") or "")
            result = {"user_name": user["UserPrincipalName"], "employee_name": user["DisplayName"],
                      "masked_password": pwd[:2] + "•" * 8 + pwd[-2:], "manager_name": user.get("ManagerName"),
                      "manager_email": user.get("ManagerEmail"), "password_token": token}
            msg = f"Password reset successful for {user['UserPrincipalName']}."
        elif intent == "account_unlock":
            user["LockedOut"] = False
            user["BadPasswordCount"] = 0
            result = {"user_principal_name": user["UserPrincipalName"], "locked_out": False,
                      "unlocked_at": _now().strftime("%d %b %Y, %H:%M UTC")}
            msg = f"Account unlocked for {user['UserPrincipalName']}."
        elif intent == "failed_login_investigation":
            result = {"report": _sample_report(email)}
            msg = "Investigation complete."
        else:
            result = {"user_principal_name": user["UserPrincipalName"], "group": "TechAI_Group", "status": "applied"}
            msg = "Group membership updated."

        response.update(success=True, message=msg, tool_result={"success": True, "message": msg, "result": result})
        self._record(query, intent, email, "completed", request_id)
        return response

    @staticmethod
    def _record(query: str, intent: str, email: str, status: str, request_id: str | None = None) -> None:
        for item in _HISTORY:  # a confirmation retry updates the same audit row, like the real DB
            if request_id and item["request_id"] == request_id:
                item["status"] = status
                return
        _HISTORY.insert(0, {"request_id": request_id or uuid.uuid4().hex, "request": query, "operation": intent,
                            "target": email, "status": status, "requested_at": _now()})


# --- flow_service-compatible helpers -------------------------------------------------

def get_config_status() -> Dict[str, Any]:
    return {"ollama_host": "preview", "model_name": "preview", "graph_client_id": True,
            "graph_client_secret": True, "graph_tenant_id": True, "config_valid": True,
            "orchestration_engine": "langgraph", "operation_audit_enabled": True,
            "powershell_operations_enabled": False, "destructive_operations_enabled": False,
            "requester_role": "helpdesk", "mode": "UI preview (sample data)"}


def check_ollama() -> tuple[bool, str]:
    return True, "Preview mode: no model is called."


def email_is_configured() -> bool:
    return False


def build_password_download(token: str):
    entry = _VAULT.get(token)
    if entry is None:
        return False, None, None, "That password reset is no longer available. Run the reset again."
    content = (f"TechAdmin temporary password (PREVIEW - not a real credential)\n\nUser: {entry.username}\n"
               f"Employee: {entry.employee_name}\nTemporary password: {entry.password}\n")
    return True, f"techadmin_{entry.username.split('@')[0]}_password.txt", content, ""


def send_password_to_manager(token: str):
    return False, "Email delivery is disabled in preview mode.", ""


def get_user_request_history(user_id: str, limit: int = 20) -> list[dict[str, Any]]:
    del user_id
    _seed_history()
    return _HISTORY[:limit]


def authorize_preview(claims: dict[str, Any]) -> dict[str, Any]:
    name = claims.get("name") or "TechAdmin User"
    return {"display_name": name, "allowed": True, "reason": "preview_mode", "message": "",
            "user_principal_name": claims.get("preferred_username") or "", "user_id": "preview-user",
            "department": "IT Operations"}
