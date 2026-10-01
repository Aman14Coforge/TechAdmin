"""Output guardrails for TechAdmin."""
from __future__ import annotations

import copy
from typing import Any, Dict, List, Tuple

from loguru import logger

from App.guardrails.policy import (
    ALLOWED_COMPUTER_FIELDS,
    ALLOWED_USER_FIELDS,
    DISPLAY_SAFE_FIELDS,
    HARD_SECRET_MARKERS,
    MSG_PASSWORD_DELIVERED,
    SENSITIVE_FIELD_MARKERS,
    SHOW_ALL_USER_FIELDS,
    SHOW_TEMPORARY_PASSWORD,
)

REDACTED = "[redacted]"


def is_sensitive_field(field_name: str) -> bool:
    if field_name in DISPLAY_SAFE_FIELDS:
        return False

    normalized = field_name.lower().replace("_", "").replace("-", "")
    return any(
        marker.replace("_", "").replace("-", "") in normalized
        for marker in SENSITIVE_FIELD_MARKERS
    )


def is_hard_secret(field_name: str) -> bool:
    if field_name in DISPLAY_SAFE_FIELDS:
        return False

    normalized = field_name.lower().replace("_", "").replace("-", "")
    return any(marker in normalized for marker in HARD_SECRET_MARKERS)


def _filter_record(
    record: Dict[str, Any],
    allowed_fields: set[str],
) -> Tuple[Dict[str, Any], List[str]]:
    if not isinstance(record, dict):
        return record, []

    filtered: Dict[str, Any] = {}
    removed: List[str] = []

    for key, value in record.items():
        if key in allowed_fields:
            filtered[key] = value
        else:
            removed.append(key)

    return filtered, removed


def filter_user_record(
    record: Dict[str, Any],
) -> Tuple[Dict[str, Any], List[str]]:
    return _filter_record(record, ALLOWED_USER_FIELDS)


def filter_computer_record(
    record: Dict[str, Any],
) -> Tuple[Dict[str, Any], List[str]]:
    return _filter_record(record, ALLOWED_COMPUTER_FIELDS)


def redact_sensitive(
    payload: Any,
    removed: List[str] = None,
) -> Tuple[Any, List[str]]:
    removed = removed if removed is not None else []

    if isinstance(payload, dict):
        cleaned = {}
        for key, value in payload.items():
            if is_sensitive_field(key):
                cleaned[key] = REDACTED
                removed.append(key)
            else:
                cleaned[key], _ = redact_sensitive(value, removed)
        return cleaned, removed

    if isinstance(payload, list):
        return [
            redact_sensitive(item, removed)[0]
            for item in payload
        ], removed

    return payload, removed


def _restore_except_hard_secrets(
    record: Dict[str, Any],
    allow: set = None,
) -> Tuple[Dict[str, Any], List[str]]:
    allow = allow or set()
    restored = {}
    withheld = []

    for key, value in record.items():
        if key in allow or not is_hard_secret(key):
            restored[key] = value
        else:
            restored[key] = REDACTED
            withheld.append(key)

    return restored, withheld


def _result_dict(
    tool_result: Dict[str, Any] | None,
) -> Dict[str, Any] | None:
    if not isinstance(tool_result, dict):
        return None
    value = tool_result.get("result")
    return value if isinstance(value, dict) else None


def sanitize_response(
    response: Dict[str, Any],
    intent: str = "",
) -> Dict[str, Any]:
    if not isinstance(response, dict):
        return response

    normalized_intent = str(
        getattr(intent, "value", intent) or ""
    ).strip().casefold()

    sanitized = copy.deepcopy(response)
    all_removed: List[str] = []

    original_tool_result = response.get("tool_result")
    original_result = copy.deepcopy(_result_dict(original_tool_result))
    original_message = response.get("message")

    tool_result = sanitized.get("tool_result")
    result = _result_dict(tool_result)

    if isinstance(tool_result, dict) and isinstance(result, dict):
        # Preserve the existing Get User Details allowlist behavior. Support
        # both a raw user dictionary and the current {backend, user, execution}
        # wrapper shape.
        if normalized_intent == "get_user_details" and not SHOW_ALL_USER_FIELDS:
            user_record = result.get("user")
            if isinstance(user_record, dict):
                filtered, removed = filter_user_record(user_record)
                result["user"] = filtered
            else:
                filtered, removed = filter_user_record(result)
                tool_result["result"] = filtered
                result = filtered
            all_removed.extend(removed)

        # Apply a dedicated allowlist to only the computer data. Keep wrapper
        # fields such as backend and execution intact for existing diagnostics.
        if normalized_intent == "get_computer_details":
            computer = result.get("computer")
            if isinstance(computer, dict):
                filtered_computer, removed = filter_computer_record(computer)
                result["computer"] = filtered_computer
                all_removed.extend(removed)

        if (
            normalized_intent == "password_reset"
            and not SHOW_TEMPORARY_PASSWORD
        ):
            if "new_password" in result:
                result.pop("new_password", None)
                all_removed.append("new_password")

            tool_result["message"] = MSG_PASSWORD_DELIVERED
            sanitized["message"] = MSG_PASSWORD_DELIVERED

    sanitized, redacted = redact_sensitive(sanitized)
    all_removed.extend(redacted)

    restored_tool_result = sanitized.get("tool_result")
    restored_result = _result_dict(restored_tool_result)

    if (
        isinstance(restored_tool_result, dict)
        and isinstance(restored_result, dict)
        and isinstance(original_result, dict)
    ):
        if normalized_intent == "get_user_details" and SHOW_ALL_USER_FIELDS:
            original_user = original_result.get("user")
            if isinstance(original_user, dict):
                restored_user, still_hidden = _restore_except_hard_secrets(
                    original_user
                )
                restored_result["user"] = restored_user
                all_removed = [
                    name for name in all_removed if name not in restored_user
                ] + still_hidden
            else:
                restored, still_hidden = _restore_except_hard_secrets(
                    original_result
                )
                restored_tool_result["result"] = restored
                all_removed = [
                    name for name in all_removed if name not in restored
                ] + still_hidden

        if (
            normalized_intent == "password_reset"
            and SHOW_TEMPORARY_PASSWORD
        ):
            restored, still_hidden = _restore_except_hard_secrets(
                original_result,
                allow={"new_password"},
            )
            restored_tool_result["result"] = restored
            restored_tool_result["message"] = original_message
            sanitized["message"] = original_message
            all_removed = [
                name for name in all_removed if name not in restored
            ] + still_hidden

    if all_removed:
        logger.info(
            "GUARDRAIL_OUTPUT_FILTERED | intent={} | removed_fields={}",
            normalized_intent or "unknown",
            sorted(set(all_removed)),
        )
        sanitized["guardrails_output_filtered"] = sorted(set(all_removed))

    return sanitized
