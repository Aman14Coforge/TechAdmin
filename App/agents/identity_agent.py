from __future__ import annotations

import logging
from collections.abc import Callable

from App.agents.tools.account_unlock_tool import (
    unlock_account_tool,
)
from App.agents.tools.grant_revoke_access_tool import (
    grant_revoke_access_tool,
)
from App.agents.tools.investigate_failed_login_tool import (
    investigate_failed_login_tool,
)
from App.agents.tools.password_reset_tool import (
    reset_password_tool,
)
from App.schemas.models import (
    AuditEvent,
    Intent,
    ToolRequest,
    ToolResult,
    WorkflowState,
)


logger = logging.getLogger(__name__)


ToolFunction = Callable[
    [ToolRequest],
    ToolResult,
]


TOOL_REGISTRY: dict[Intent, ToolFunction] = {
    Intent.PASSWORD_RESET: reset_password_tool,
    Intent.ACCOUNT_UNLOCK: unlock_account_tool,
    Intent.GRANT_ACCESS: grant_revoke_access_tool,
    Intent.REVOKE_ACCESS: grant_revoke_access_tool,
    Intent.FAILED_LOGIN_INVESTIGATION:
        investigate_failed_login_tool,
}


def identity_agent_node(
    state: WorkflowState,
) -> dict:
    """
    Dispatches a validated Identity intent to exactly one registered
    placeholder tool.

    The LLM does not choose the Python function. The registry performs
    deterministic intent-to-tool mapping.
    """

    if state.error:
        logger.warning(
            "TOOL_SKIPPED correlation_id=%s reason=upstream_error",
            state.correlation_id,
        )

        return {
            "selected_agent": None,
            "tool_called": None,
            "tool_result": None,
            "events": state.events
            + [
                AuditEvent(
                    event="tool_skipped",
                    detail=(
                        "Tool execution skipped because intent "
                        "analysis failed."
                    ),
                )
            ],
        }

    if state.intent is None:
        logger.warning(
            "TOOL_SKIPPED correlation_id=%s reason=intent_missing",
            state.correlation_id,
        )

        return {
            "selected_agent": None,
            "tool_called": None,
            "tool_result": None,
            "events": state.events
            + [
                AuditEvent(
                    event="tool_skipped",
                    detail="No classified intent was available.",
                )
            ],
        }

    if state.validation is None:
        logger.warning(
            "TOOL_SKIPPED correlation_id=%s "
            "intent=%s reason=validation_missing",
            state.correlation_id,
            state.intent.value,
        )

        return {
            "selected_agent": None,
            "tool_called": None,
            "tool_result": None,
            "events": state.events
            + [
                AuditEvent(
                    event="tool_skipped",
                    detail="Validation result was not available.",
                )
            ],
        }

    if not state.validation.is_valid:
        logger.info(
            "TOOL_SKIPPED correlation_id=%s "
            "intent=%s missing_fields=%s rejected_fields=%s",
            state.correlation_id,
            state.intent.value,
            state.validation.missing_fields,
            state.validation.rejected_fields,
        )

        return {
            "selected_agent": None,
            "tool_called": None,
            "tool_result": None,
            "events": state.events
            + [
                AuditEvent(
                    event="tool_skipped",
                    detail=(
                        f"Tool not called for "
                        f"{state.intent.value}. "
                        f"Missing fields: "
                        f"{state.validation.missing_fields}."
                    ),
                )
            ],
        }

    tool_function = TOOL_REGISTRY.get(
        state.intent,
    )

    if tool_function is None:
        logger.warning(
            "TOOL_SKIPPED correlation_id=%s "
            "intent=%s reason=tool_not_registered",
            state.correlation_id,
            state.intent.value,
        )

        return {
            "selected_agent": None,
            "tool_called": None,
            "tool_result": None,
            "events": state.events
            + [
                AuditEvent(
                    event="tool_skipped",
                    detail=(
                        f"No Identity tool is registered for "
                        f"{state.intent.value}."
                    ),
                )
            ],
        }

    tool_request = ToolRequest(
        correlation_id=state.correlation_id,
        intent=state.intent,
        fields=state.fields,
    )

    logger.info(
        "TOOL_DISPATCH correlation_id=%s "
        "intent=%s selected_agent=identity_agent "
        "selected_tool=%s",
        state.correlation_id,
        state.intent.value,
        tool_function.__name__,
    )

    tool_result = tool_function(
        tool_request,
    )

    logger.info(
        "TOOL_COMPLETED correlation_id=%s "
        "intent=%s tool=%s status=%s operation_id=%s",
        state.correlation_id,
        state.intent.value,
        tool_result.tool.value,
        tool_result.status.value,
        tool_result.operation_id,
    )

    return {
        "selected_agent": "identity_agent",
        "tool_called": tool_result.tool,
        "tool_result": tool_result,
        "events": state.events
        + [
            AuditEvent(
                event="tool_called",
                detail=(
                    f"{tool_result.tool.value} called for "
                    f"{state.intent.value}; "
                    f"operation_id={tool_result.operation_id}"
                ),
            )
        ],
    }