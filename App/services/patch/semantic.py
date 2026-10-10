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
INVALID_DEVICES = {
    "TODAY", "TODAYS", "CURRENT", "LATEST", "DEVICE", "DEVICES",
    "PATCH", "PATCHES", "REPORT", "SECURITY", "NON-COMPLIANT",
    "NONCOMPLIANT", "COMPREHENSIVE", "IMPACT",
}

PROMPT = """
You extract metadata for an enterprise endpoint Security Agent.
Return JSON only with these keys:
action, device_name, patch_query, start_date, end_date, reason,
needs_confirmation, clarification_question, explanation.

Allowed actions:
patch_report, device_report, patch_search, patch_ticket,
eligible_ticket_batch, patch_scan, unsupported_security,
redirect_identity, unknown.

Rules:
- KB123456 and Q123456 are patch identifiers, never device names.
- A device is an explicit hostname.
- Ticket and live scan actions require confirmation.
- Never invent metadata.

Request: {request}
"""


class PatchSemanticInterpreter:
    ROUTING_TERMS = (
        "patch", "ivanti", "non-compliant", "noncompliant", "missing update",
        "missing patches", "vulnerability", "kb", "endpoint security",
        "software install",
    )
    IDENTITY_TERMS = (
        "password", "unlock account", "user details", "add user",
        "remove user", "group access", "create user", "delete user",
    )

    @classmethod
    def matches(cls, text: str) -> bool:
        normalized = str(text or "").casefold()
        return any(term in normalized for term in cls.ROUTING_TERMS)

    def interpret(
        self,
        text: str,
        *,
        selected_device: str | None = None,
    ) -> dict[str, Any]:
        query = str(text or "").strip()
        low = query.casefold()

        if not query:
            return self._result(
                "unknown",
                clarification="What endpoint-security operation do you need?",
            )

        if any(term in low for term in self.IDENTITY_TERMS):
            return self._result("redirect_identity")

        if "software" in low and any(
            word in low for word in ("install", "uninstall", "deploy", "remove")
        ):
            return self._result(
                "unsupported_security",
                explanation="Ivanti software deployment is not implemented yet.",
            )

        patch_identifier = self._extract_patch(query)
        device_name = self._extract_device(query)

        # Trusted precedence: patch identifiers can never be interpreted as devices.
        if patch_identifier:
            return self._result("patch_search", patch=patch_identifier)

        if "scan" in low:
            return self._result("patch_scan", confirm=True)

        if "ticket" in low:
            contextual_device = None
            if any(
                phrase in low
                for phrase in ("this device", "selected device", "that device")
            ):
                contextual_device = self._clean_device(selected_device)

            target = device_name or contextual_device
            if not target:
                return self._result(
                    "patch_ticket",
                    reason=query,
                    clarification="Which device should receive the patch-remediation ticket?",
                )
            return self._result(
                "patch_ticket",
                device=target,
                reason=query,
                confirm=True,
            )

        if device_name and any(
            term in low
            for term in (
                "history", "device", "report", "missing patch", "details",
                "non-compliant", "noncompliant", "compliance", "vulnerability",
            )
        ):
            return self._result("device_report", device=device_name)

        if device_name:
            return self._result("device_report", device=device_name)

        if any(
            term in low
            for term in (
                "today", "today's", "todays", "latest", "current",
                "all non-compliant", "all noncompliant", "all devices",
                "all device", "fleet",
            )
        ):
            today = date.today().isoformat()
            return self._result("patch_report", start=today, end=today)

        if any(
            term in low
            for term in ("non-compliant", "noncompliant", "missing patches", "ivanti patch")
        ):
            return self._result("patch_report")

        try:
            response = ChatOllama(
                model=settings.ai_model,
                base_url=settings.ollama_host,
                temperature=0,
                format="json",
            ).invoke(PROMPT.format(request=query))
            parsed = json.loads(response.content)
            if not isinstance(parsed, dict):
                raise ValueError("Invalid semantic response")

            llm_patch = self._extract_patch(str(parsed.get("patch_query") or ""))
            if llm_patch:
                return self._result("patch_search", patch=llm_patch)

            action = str(parsed.get("action") or "unknown")
            llm_device = self._clean_device(parsed.get("device_name"))
            if action == "device_report" and not llm_device:
                return self._result(
                    "device_report",
                    clarification="Which device should I use for the patch-history report?",
                )

            return self._result(
                action,
                device=llm_device,
                patch=parsed.get("patch_query"),
                start=parsed.get("start_date"),
                end=parsed.get("end_date"),
                reason=parsed.get("reason"),
                confirm=bool(parsed.get("needs_confirmation")),
                clarification=parsed.get("clarification_question"),
                explanation=str(parsed.get("explanation") or ""),
            )
        except Exception:
            return self._result(
                "unknown",
                clarification=(
                    "Provide a device name, patch or KB identifier, "
                    "or a fleet-compliance request."
                ),
            )

    @staticmethod
    def _extract_patch(text: str) -> str | None:
        match = PATCH_ID_RE.search(str(text or ""))
        return match.group(0).upper() if match else None

    @staticmethod
    def _clean_device(value: Any) -> str | None:
        candidate = str(value or "").strip().upper()
        if (
            not candidate
            or candidate in INVALID_DEVICES
            or PATCH_ID_RE.fullmatch(candidate)
            or re.fullmatch(r"20\d{2}-\d{2}-\d{2}", candidate)
        ):
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
        }
