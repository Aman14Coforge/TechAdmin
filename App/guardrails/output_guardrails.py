"""
Output Guardrails
Author: Amit Bhagat
Purpose: Strip sensitive values out of anything on its way to the user.

Covers sections 2.2, 2.4 and 3.3 of the guardrails design document:

  - minimum data exposure, via a field allowlist for user records
  - output filtering at every nesting depth
  - password exposure prevention

The design here is allowlist first, blocklist second. User records are reduced
to the approved fields, so a field Graph adds next year is withheld by default
rather than leaking until someone notices. The blocklist then runs over
everything else, including nested tool payloads that have no fixed shape.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

from loguru import logger

from App.guardrails.policy import (
    ALLOWED_USER_FIELDS,
    MSG_PASSWORD_DELIVERED,
    HARD_SECRET_MARKERS,
    SENSITIVE_FIELD_MARKERS,
    SHOW_ALL_USER_FIELDS,
    SHOW_TEMPORARY_PASSWORD,
)

REDACTED = "[redacted]"


def is_sensitive_field(field_name: str) -> bool:
    """
    Decide whether a field name marks a value that must not be shown.

    Matching is on normalised substrings, so passwordHash, password_hash,
    PasswordHash and newPassword all match the "password" marker.

    Args:
        field_name: The key to test.

    Returns:
        True when the field must be removed or redacted.
    """
    normalized = field_name.lower().replace("_", "").replace("-", "")
    return any(
        marker.replace("_", "").replace("-", "") in normalized
        for marker in SENSITIVE_FIELD_MARKERS
    )


def is_hard_secret(field_name: str) -> bool:
    """
    Decide whether a field stays hidden even with the demo switches on.

    "Show everything the API returned" means the contact and organisation
    fields, not credentials. A password hash or an access token is never demo
    material.

    Args:
        field_name: The key to test.

    Returns:
        True when the field must stay redacted regardless of the switches.
    """
    normalized = field_name.lower().replace("_", "").replace("-", "")
    return any(marker in normalized for marker in HARD_SECRET_MARKERS)


def filter_user_record(record: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
    """
    Reduce a Graph user record to the approved fields.

    Section 2.2. An allowlist, so anything not explicitly approved is dropped.

    Args:
        record: The raw user record from Microsoft Graph.

    Returns:
        Tuple of (filtered record, names of the fields that were removed).
    """
    if not isinstance(record, dict):
        return record, []

    filtered = {}
    removed = []

    for key, value in record.items():
        if key in ALLOWED_USER_FIELDS:
            filtered[key] = value
        else:
            removed.append(key)

    return filtered, removed


def redact_sensitive(payload: Any, removed: List[str] = None) -> Tuple[Any, List[str]]:
    """
    Walk any structure and remove sensitive values wherever they appear.

    Section 2.4. Recursive because tool payloads nest, and a password two levels
    down is exactly as exposed as one at the top.

    The key is kept with a redaction marker rather than deleted, so the response
    still shows that a value existed. A silently missing field looks like a bug;
    a visible [redacted] looks like policy.

    Args:
        payload: Any dict, list or scalar.
        removed: Accumulator for the names of redacted fields.

    Returns:
        Tuple of (cleaned payload, names of the fields that were redacted).
    """
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
        return [redact_sensitive(item, removed)[0] for item in payload], removed

    return payload, removed


def _restore_except_hard_secrets(
    record: Dict[str, Any],
    allow: set = None,
) -> Tuple[Dict[str, Any], List[str]]:
    """
    Put the original fields back, minus anything that is a hard secret.

    Args:
        record: The untouched payload kept aside before filtering.
        allow: Keys to restore even though they look like secrets. Used for
            new_password, which the demo switch exists to expose.

    Returns:
        Tuple of (restored record, names of the fields still withheld).
    """
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


def sanitize_response(
    response: Dict[str, Any],
    intent: str = "",
) -> Dict[str, Any]:
    """
    Clean a completed flow response before it reaches the user.

    Runs four passes:

      1. reduce the user record under tool_result.result to approved fields
      2. replace the password reset message with the approved wording
      3. redact any remaining sensitive field, at any depth
      4. restore whatever the demo visibility switches exempt

    Passes 1 and 2 are skipped when SHOW_ALL_USER_FIELDS and
    SHOW_TEMPORARY_PASSWORD are set. Pass 3 always runs, so a field the
    switches do not cover is still redacted.

    Args:
        response: The response dict built by the flow.
        intent: The resolved intent, used to pick the right treatment.

    Returns:
        A new response dict. The original is not modified, so the unfiltered
        version stays available for the audit log.
    """
    if not isinstance(response, dict):
        return response

    import copy

    sanitized = copy.deepcopy(response)
    all_removed: List[str] = []

    # Kept aside before any pass runs, so a value a demo switch exempts can be
    # put back after the blanket redaction rather than having to thread an
    # allowlist through the recursion.
    original_result = copy.deepcopy(
        ((response.get("tool_result") or {}).get("result"))
        if isinstance(response.get("tool_result"), dict)
        else None
    )
    original_message = response.get("message")

    tool_result = sanitized.get("tool_result")

    if isinstance(tool_result, dict):
        result = tool_result.get("result")

        # Pass 1: allowlist the user record, unless the demo switch is on.
        if (
            intent == "get_user_details"
            and isinstance(result, dict)
            and not SHOW_ALL_USER_FIELDS
        ):
            filtered, removed = filter_user_record(result)
            tool_result["result"] = filtered
            all_removed.extend(removed)

        # Pass 2: a reset must never return the password it generated, unless
        # the demo switch is on.
        if (
            intent == "password_reset"
            and isinstance(result, dict)
            and not SHOW_TEMPORARY_PASSWORD
        ):
            if "new_password" in result:
                result.pop("new_password", None)
                all_removed.append("new_password")

            # The tool writes the password into its message too.
            tool_result["message"] = MSG_PASSWORD_DELIVERED
            sanitized["message"] = MSG_PASSWORD_DELIVERED

    # Pass 3: catch anything the first two passes did not cover.
    sanitized, redacted = redact_sensitive(sanitized)
    all_removed.extend(redacted)

    # Pass 4: restore what the demo switches exempt. Pass 3 redacts by field
    # name, so it would blank out new_password and any Graph field whose name
    # trips a marker; putting the originals back is what makes the switches
    # actually take effect.
    restored_tool_result = sanitized.get("tool_result")

    if isinstance(restored_tool_result, dict) and isinstance(original_result, dict):
        if intent == "get_user_details" and SHOW_ALL_USER_FIELDS:
            restored, still_hidden = _restore_except_hard_secrets(original_result)
            restored_tool_result["result"] = restored
            all_removed = [
                name for name in all_removed if name not in restored
            ] + still_hidden

        if intent == "password_reset" and SHOW_TEMPORARY_PASSWORD:
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
        # The names of removed fields are safe to log; their values are not,
        # and are never written here.
        logger.info(
            "GUARDRAIL_OUTPUT_FILTERED | intent={} | removed_fields={}",
            intent or "unknown",
            sorted(set(all_removed)),
        )
        sanitized["guardrails_output_filtered"] = sorted(set(all_removed))

    return sanitized
