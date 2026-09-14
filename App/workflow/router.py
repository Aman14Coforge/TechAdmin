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
    Select the agent family for a classified intent.

    The router selects only the agent. The selected agent is responsible
    for validation, MCP server selection and MCP tool selection.
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

        IntentType.CREATE_USER:
            AgentType.IDENTITY,

        IntentType.DELETE_USER:
            AgentType.IDENTITY,

        IntentType.CREATE_GROUP:
            AgentType.IDENTITY,

        IntentType.CREATE_VM:
            AgentType.IDENTITY,
    }

    def route(
        self,
        intent: str | IntentType,
        metadata: dict | None = None,
    ) -> RoutingResult:
        """
        Route a classified intent to an agent.

        Args:
            intent:
                Intent string or IntentType.

            metadata:
                Extracted metadata. Kept for compatibility and future
                routing policies.

        Returns:
            Validated RoutingResult.

        Raises:
            ValueError:
                If the intent is unknown or no agent is registered.
        """

        try:
            normalized_intent = (
                intent
                if isinstance(
                    intent,
                    IntentType,
                )
                else IntentType(
                    intent.strip().casefold()
                )
            )

        except (
            ValueError,
            AttributeError,
        ) as exc:
            logger.warning(
                "AGENT_ROUTING_REJECTED | "
                "intent={} | reason=invalid_intent",
                intent,
            )

            raise ValueError(
                f"Unsupported intent: {intent}"
            ) from exc

        if normalized_intent is IntentType.UNKNOWN:
            logger.warning(
                "AGENT_ROUTING_REJECTED | "
                "intent=unknown"
            )

            raise ValueError(
                "The request does not match a supported "
                "TechAdmin operation."
            )

        agent_type = (
            self.INTENT_AGENT_MAPPING.get(
                normalized_intent
            )
        )

        if agent_type is None:
            logger.error(
                "AGENT_ROUTING_FAILED | "
                "intent={} | "
                "reason=no_registered_agent",
                normalized_intent.value,
            )

            raise ValueError(
                f"No agent is registered for intent "
                f"'{normalized_intent.value}'."
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
            "AGENT_ROUTED | "
            "intent={} | "
            "selected_agent={} | "
            "metadata_fields={}",
            normalized_intent.value,
            result.agent_name,
            sorted(
                metadata.keys()
                if isinstance(metadata, dict)
                else []
            ),
        )

        return result

    def get_supported_agents(
        self,
    ) -> list:
        """
        Return all registered agent names.
        """

        return sorted(
            {
                f"{agent.value}_agent"
                for agent
                in self.INTENT_AGENT_MAPPING.values()
            }
        )

    def get_supported_intents(
        self,
    ) -> list:
        """
        Return every intent registered with the router.
        """

        return sorted(
            intent.value
            for intent
            in self.INTENT_AGENT_MAPPING
        )