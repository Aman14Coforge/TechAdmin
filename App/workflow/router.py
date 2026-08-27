"""
Agent Router Module
Author: Shreesanyog
Purpose: Route requests to appropriate agents based on intent
"""

from typing import Dict, Any
from loguru import logger


class AgentRouter:
    """
    Routes user requests to the appropriate agent based on identified intent.
    Supported agents: identity_agent, network_agent, patch_agent
    """
    
    def __init__(self):
        """Initialize the router with available agents."""
        self.agents = {
            "password_reset": "identity_agent",
            "account_unlock": "identity_agent",
            "grant_access": "identity_agent",
            "revoke_access": "identity_agent",
            "get_user_details": "identity_agent",
            "guest_wifi": "network_agent",
            "connectivity_check": "network_agent",
            "software_install": "patch_agent",
            "patch_management": "patch_agent"
        }
        logger.info("AgentRouter initialized")
    
    def route(self, intent: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """
        Route request to appropriate agent.
        
        Args:
            intent: The identified intent
            metadata: Extracted metadata from user input
            
        Returns:
            Dict containing:
            - agent_name: Name of the agent to execute
            - agent_type: Type of agent (identity, network, patch)
            - metadata: Metadata to pass to agent
            - routing_reason: Why this agent was selected
        """
        logger.info(f"Routing intent '{intent}' to appropriate agent")
        
        agent_type = self.agents.get(intent, None)
        
        if not agent_type:
            logger.error(f"No agent found for intent: {intent}")
            raise ValueError(f"Unsupported intent: {intent}")
        
        routing_info = {
            "agent_name": agent_type,
            "agent_type": agent_type.split("_")[0],  # e.g., "identity" from "identity_agent"
            "metadata": metadata,
            "routing_reason": f"Intent '{intent}' maps to {agent_type}"
        }
        
        logger.info(f"Routing info: {routing_info}")
        return routing_info
    
    def get_supported_agents(self) -> list:
        """Get list of supported agents."""
        return list(set(self.agents.values()))
