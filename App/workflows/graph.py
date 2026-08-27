from __future__ import annotations

import logging

from langgraph.graph import (
    END,
    START,
    StateGraph,
)

from App.agents.identity_agent import (
    identity_agent_node,
)
from App.intent.analyzer import IntentAnalyzer
from App.intent.validator import validate
from App.schemas.models import (
    AuditEvent,
    WorkflowState,
    WorkflowStatus,
)


logger = logging.getLogger(__name__)


def build_graph(
    analyzer: IntentAnalyzer,
):
    def intent_node(
        state: WorkflowState,
    ) -> dict:
        try:
            extraction = analyzer.analyze(
                state.user_query,
            )

            fields, validation = validate(
                state.user_query,
                extraction,
            )

            logger.info(
                "INTENT_EXTRACTED "
                "correlation_id=%s "
                "intent=%s "
                "confidence=%s "
                "username=%s "
                "username_source=%s "
                "email=%s "
                "employee_id=%s "
                "missing_fields=%s",
                state.correlation_id,
                extraction.intent.value,
                extraction.confidence,
                fields.username,
                fields.username_source,
                fields.email,
                fields.employee_id,
                validation.missing_fields,
            )

            return {
                "intent":
                    extraction.intent,

                "confidence":
                    extraction.confidence,

                "fields":
                    fields,

                "validation":
                    validation,

                "workflow_status":
                    (
                        WorkflowStatus.READY_FOR_TOOL
                        if validation.is_valid
                        else WorkflowStatus.NEEDS_INPUT
                    ),

                "events":
                    state.events
                    + [
                        AuditEvent(
                            event=(
                                "intent_extracted"
                            ),
                            detail=(
                                f"intent="
                                f"{extraction.intent.value}; "
                                f"valid="
                                f"{validation.is_valid}; "
                                f"missing="
                                f"{validation.missing_fields}; "
                                f"derived="
                                f"{validation.derived_fields}"
                            ),
                        )
                    ],
            }

        except Exception as exc:
            logger.exception(
                "INTENT_ANALYSIS_FAILED "
                "correlation_id=%s "
                "error_type=%s",
                state.correlation_id,
                type(exc).__name__,
            )

            return {
                "workflow_status":
                    WorkflowStatus.FAILED,

                "error": (
                    "Intent analysis could not be "
                    "completed. Check the configured "
                    "LLM provider and credentials."
                ),

                "events":
                    state.events
                    + [
                        AuditEvent(
                            event="intent_failed",
                            detail=type(
                                exc
                            ).__name__,
                        )
                    ],
            }

    graph = StateGraph(
        WorkflowState,
    )

    graph.add_node(
        "intent",
        intent_node,
    )

    graph.add_node(
        "identity_agent",
        identity_agent_node,
    )

    graph.add_edge(
        START,
        "intent",
    )

    graph.add_edge(
        "intent",
        "identity_agent",
    )

    graph.add_edge(
        "identity_agent",
        END,
    )

    return graph.compile()