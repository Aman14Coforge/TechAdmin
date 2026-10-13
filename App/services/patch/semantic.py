"""Deterministic-first interpretation for TechAdmin Security Agent."""
from __future__ import annotations

import json
import re
from datetime import date
from typing import Any

from langchain_ollama import ChatOllama

from App.services.patch.config import settings

PATCH_ID_RE = re.compile(r"\b(?:KB|Q)\d{5,12}\b", re.IGNORECASE)
DEVICE_RE = re.compile(
    r"\b(?=[A-Z0-9-]{5,64}\b)(?=[A-Z0-9-]*(?:\d|-))[A-Z0-9][A-Z0-9-]*\b",
    re.IGNORECASE,
)
DATE_RE = re.compile(r"\b20\d{2}-\d{2}-\d{2}\b")
INVALID_DEVICES = {
    "TODAY", "TODAYS", "CURRENT", "LATEST", "DEVICE", "DEVICES",
    "PATCH", "PATCHES", "REPORT", "SECURITY", "NON-COMPLIANT",
    "NONCOMPLIANT", "COMPLIANCE", "COMPLIANT", "COMPIANCE", "FLEET",
    "ALL", "SHOW", "LIST",
}

PROMPT = """You extract metadata for an enterprise endpoint Security Agent.
Return JSON only with these keys: action, device_name, patch_query, start_date,
end_date, reason, needs_confirmation, clarification_question, explanation.
Allowed actions: device_list, patch_report, device_report, patch_search,
patch_ticket, eligible_ticket_batch, patch_scan, unsupported_security,
redirect_identity, unknown.
Use device_list for show/list requests. Use patch_report only when the user
explicitly asks for a report, summary, analysis, insight, or trend. KB IDs are
patch identifiers, never device names. Preserve exact patch-name queries.
Never invent metadata. Ticket and live scan actions require confirmation.
Request: {request}
"""


class PatchSemanticInterpreter:
    ROUTING_TERMS = (
        "patch", "ivanti", "non-compliant", "noncompliant", "non compliant",
        "non compliance", "non-compliance", "noncompliance", "non compiance", "non-compiance",
        "compliance", "compliant", "missing update", "missing patches",
        "vulnerability", "kb", "endpoint", "security", "fleet", "asset",
        "software install", "show all", "list devices", "resolved devices",
    )
    IDENTITY_TERMS = (
        "password", "unlock account", "user details", "add user",
        "remove user", "group access", "create user", "delete user",
    )
    IDENTITY_REQUEST_PATTERNS = (
        (
            r"\b(?:reset|change|replace|generate|issue|recover|forgot|forget)\b"
            r".{0,40}\bpasswords?\b|\bpasswords?\b.{0,40}"
            r"\b(?:reset|change|replace|generate|issue|recover)\b"
        ),
        (
            r"\b(?:unlock|unblock)\b.{0,30}\b(?:user|account)\b|"
            r"\b(?:user|account)\b.{0,30}\b(?:unlock|unblock)\b"
        ),
        (
            r"\b(?:get|show|find|retrieve|look\s+up|lookup|check|view|inspect|pull\s+up)\b"
            r".{0,40}\b(?:user|account|employee)\b.{0,40}"
            r"\b(?:details?|information|profile|status|record)\b|"
            r"\b(?:get|show|find|retrieve|look\s+up|lookup|check|view|inspect|pull\s+up)\b"
            r".{0,40}\b(?:details?|information|profile|status|record)\b.{0,40}"
            r"\b(?:user|account|employee)\b"
        ),
        (
            r"\b(?:get|show|find|retrieve|look\s+up|lookup|check|view|inspect|pull\s+up)\b"
            r".{0,40}\b(?:details?|information|profile)\b"
        ),
        r"\b(?:grant|give|provide|revoke|remove|withdraw)\b.{0,40}\baccess\b",
        r"\b(?:add|assign|put|place|include|remove|take|revoke)\b.{0,60}\b(?:user|member|group|access)\b",
        (
            r"\b(?:investigate|diagnose|explain|review|why|find\s+out)\b.{0,50}"
            r"\b(?:failed\s+(?:sign[\s-]?ins?|logins?)|authentication failures?|"
            r"(?:account\s+)?lockouts?|locked out)\b"
        ),
        (
            r"\b(?:failed\s+(?:sign[\s-]?ins?|logins?)|authentication failures?|"
            r"(?:account\s+)?lockouts?|locked out)\b.{0,50}"
            r"\b(?:investigate|diagnose|explain|review|cause|why)\b"
        ),
        (
            r"\b(?:why|what caused|cause of)\b.{0,30}"
            r"\b(?:account\s+)?(?:lockouts?|locked(?:\s+out)?)\b"
        ),
    )
    REPORT_TERMS = ("report", "summary", "insight", "analysis", "analytics", "trend")
    LIST_TERMS = ("show", "list", "display", "which devices", "find devices")
    NONCOMPLIANCE_TERMS = (
        "non-compliant", "noncompliant", "non compliant", "non compliance", "non-compliance",
        "noncompliance", "non compiance", "non-compiance", "missing patches",
        "missing updates", "all devices", "all endpoints", "fleet",
    )

    @classmethod
    def is_identity_request(cls, text: str) -> bool:
        """Recognize identity operations before broad endpoint-security terms."""
        normalized = str(text or "").casefold()
        return any(
            re.search(pattern, normalized)
            for pattern in cls.IDENTITY_REQUEST_PATTERNS
        )

    @classmethod
    def matches(cls, text: str) -> bool:
        value = str(text or "")
        normalized = value.casefold()
        # Identity intent always wins over broad security words/device-like IDs.
        if cls.is_identity_request(normalized):
            return False
        return (
            any(term in normalized for term in cls.ROUTING_TERMS)
            or bool(PATCH_ID_RE.search(value))
            or bool(cls._extract_device(value))
        )

    def interpret(self, text: str, *, selected_device: str | None = None) -> dict[str, Any]:
        query = str(text or "").strip()
        low = query.casefold()
        if not query:
            return self._result("unknown", clarification="What endpoint-security operation do you need?")
        if any(term in low for term in self.IDENTITY_TERMS):
            return self._result("redirect_identity")
        if "software" in low and any(word in low for word in ("install", "uninstall", "deploy", "remove")):
            return self._result("unsupported_security", explanation="Ivanti software deployment is not available here yet.")

        patch_identifier = self._extract_patch(query)
        device_name = self._extract_device(query)
        if "ticket" in low:
            contextual = self._clean_device(selected_device) if any(
                phrase in low for phrase in ("this device", "selected device", "that device")
            ) else None
            target = device_name or contextual
            if not target:
                return self._result("patch_ticket", reason=query,
                                    clarification="Which device should receive the remediation ticket?")
            return self._result("patch_ticket", device=target, reason=query, confirm=True)
        if "scan" in low:
            return self._result("patch_scan", confirm=True)
        if patch_identifier:
            return self._result("patch_search", patch=patch_identifier)

        explicit_report = any(term in low for term in self.REPORT_TERMS)
        asks_list = any(term in low for term in self.LIST_TERMS)
        mentions_scope = any(term in low for term in self.NONCOMPLIANCE_TERMS)
        resolved = "resolved" in low or "archived" in low
        match_date = DATE_RE.search(query)
        start = match_date.group(0) if match_date else None
        end = start

        if device_name:
            if explicit_report or any(word in low for word in ("history", "trend", "insight", "analysis")):
                return self._result("device_report", device=device_name, start=start, end=end)
            return self._result("device_report", device=device_name, start=start, end=end)

        if resolved:
            action="patch_report" if explicit_report else "device_list"
            return self._result(action,start=start,end=end,device_status="resolved")

        if mentions_scope or "today" in low or "latest" in low or "current" in low:
            action = "patch_report" if explicit_report else "device_list"
            return self._result(action, start=start, end=end,
                                device_status="resolved" if resolved else "all" if "all devices" in low or "all endpoints" in low else "non_compliant")
        if asks_list:
            return self._result("device_list", start=start, end=end,
                                device_status="resolved" if resolved else "all")

        try:
            response = ChatOllama(
                model=settings.ai_model,
                base_url=settings.ollama_host,
                temperature=0,
                format="json",
                timeout=30,
            ).invoke(PROMPT.format(request=query))
            parsed = json.loads(response.content)
            if not isinstance(parsed, dict):
                raise ValueError("Invalid semantic response")
            patch_query = str(parsed.get("patch_query") or "").strip()
            if patch_query:
                return self._result("patch_search", patch=patch_query[:300])
            action = str(parsed.get("action") or "unknown")
            llm_device = self._clean_device(parsed.get("device_name"))
            if action == "device_report" and not llm_device:
                return self._result("device_report", clarification="Which device should I use for the report?")
            return self._result(
                action, device=llm_device, start=parsed.get("start_date"),
                end=parsed.get("end_date"), reason=parsed.get("reason"),
                confirm=bool(parsed.get("needs_confirmation")),
                clarification=parsed.get("clarification_question"),
                explanation=str(parsed.get("explanation") or ""),
                device_status=parsed.get("device_status"),
            )
        except Exception:
            return self._result(
                "unknown",
                clarification="Try asking to show non-compliant devices, report on a named device, search a KB/patch, or review resolved devices.",
            )

    @staticmethod
    def _extract_patch(text: str) -> str | None:
        match = PATCH_ID_RE.search(str(text or ""))
        return match.group(0).upper() if match else None

    @staticmethod
    def _clean_device(value: Any) -> str | None:
        candidate = str(value or "").strip().upper()
        if not candidate or candidate in INVALID_DEVICES or PATCH_ID_RE.fullmatch(candidate):
            return None
        if DATE_RE.fullmatch(candidate):
            return None
        return candidate if DEVICE_RE.fullmatch(candidate) else None

    @classmethod
    def _extract_device(cls, text: str) -> str | None:
        for match in DEVICE_RE.finditer(str(text or "")):
            candidate = cls._clean_device(match.group(0))
            if candidate:
                return candidate
        return None

    @staticmethod
    def _result(
        action: str,
        *,
        device: str | None = None,
        patch: str | None = None,
        start: str | None = None,
        end: str | None = None,
        reason: str | None = None,
        confirm: bool = False,
        clarification: str | None = None,
        explanation: str = "",
        device_status: str | None = None,
    ) -> dict[str, Any]:
        return {
            "action": action,
            "device_name": device,
            "device_names": [],
            "patch_query": patch,
            "start_date": start,
            "end_date": end,
            "reason": reason,
            "needs_confirmation": confirm,
            "clarification_question": clarification,
            "explanation": explanation,
            "device_status": device_status,
        }
