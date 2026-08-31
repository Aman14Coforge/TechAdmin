"""
Agent Router Module

Purpose:
    Route requests to the appropriate agent based on the classified
    intent.
"""

from __future__ import annotations

from loguru import logger

from App.workflow.state import (
    AgentType,
    IntentType,
    RoutingResult,
)


class AgentRouter:
    """
    The router selects an agent family.

    The Identity Agent selects the exact tool.
    """

    INTENT_AGENT_MAPPING: dict[
        IntentType,
        AgentType,
    ] = {
        IntentType.PASSWORD_RESET:
            AgentType.IDENTITY,

        IntentType.ACCOUNT_UNLOCK:
            AgentType.IDENTITY,

        IntentType.GRANT_ACCESS:
            AgentType.IDENTITY,

        IntentType.REVOKE_ACCESS:
            AgentType.IDENTITY,

        IntentType.GET_USER_DETAILS:
            AgentType.IDENTITY,

        IntentType.FAILED_LOGIN_INVESTIGATION:
            AgentType.IDENTITY,
    }

    def route(
        self,
        intent: str | IntentType,
        metadata: dict | None = None,
    ) -> RoutingResult:
        try:
            normalized_intent = (
                intent
                if isinstance(
                    intent,
                    IntentType,
                )
                else IntentType(intent)
            )
        except ValueError as exc:
            raise ValueError(
                f"Unsupported intent: {intent}"
            ) from exc

        agent_type = (
            self.INTENT_AGENT_MAPPING.get(
                normalized_intent
            )
        )

        if agent_type is None:
            raise ValueError(
                f"No agent is registered for "
                f"intent '{normalized_intent.value}'."
            )

        result = RoutingResult(
            agent_name=(
                f"{agent_type.value}_agent"
            ),
            agent_type=agent_type,
            routing_reason=(
                f"Intent '{normalized_intent.value}' "
                f"maps to "
                f"'{agent_type.value}_agent'."
            ),
        )

        logger.info(
            "AGENT_ROUTED | intent={} | "
            "selected_agent={}",
            normalized_intent.value,
            result.agent_name,
        )

        return result

    def get_supported_agents(
        self,
    ) -> list:
        return sorted(
            {
                f"{agent.value}_agent"
                for agent in (
                    self.INTENT_AGENT_MAPPING.values()
                )
            }
        )