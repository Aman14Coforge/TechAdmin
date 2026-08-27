"""
Workflow State Module
Author: Shreesanyog
Purpose: Define the state schema for LangGraph workflow
"""

from dataclasses import dataclass
from typing import Dict, Any, Optional
from enum import Enum


class IntentType(str, Enum):
    """Supported intent types."""
    PASSWORD_RESET = "password_reset"
    ACCOUNT_UNLOCK = "account_unlock"
    GRANT_ACCESS = "grant_access"
    REVOKE_ACCESS = "revoke_access"
    GUEST_WIFI = "guest_wifi"
    CONNECTIVITY_CHECK = "connectivity_check"
    SOFTWARE_INSTALL = "software_install"
    PATCH_MANAGEMENT = "patch_management"


class AgentType(str, Enum):
    """Supported agent types."""
    IDENTITY = "identity"
    NETWORK = "network"
    PATCH = "patch"


@dataclass
class WorkflowState:
    """
    State schema for the LangGraph workflow.
    Tracks the progression through the workflow stages.
    
    TODO: Implement state persistence and transitions
    """
    
    # Input
    user_input: str
    request_id: str
    
    # Intent Classification
    intent: Optional[IntentType] = None
    intent_confidence: float = 0.0
    
    # Metadata Extraction
    metadata: Optional[Dict[str, Any]] = None
    metadata_valid: bool = False
    
    # Routing
    agent_type: Optional[AgentType] = None
    
    # Execution
    execution_result: Optional[Dict[str, Any]] = None
    execution_success: bool = False
    error_message: Optional[str] = None
    
    # Response
    user_response: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert state to dictionary."""
        return {
            "user_input": self.user_input,
            "request_id": self.request_id,
            "intent": self.intent.value if self.intent else None,
            "intent_confidence": self.intent_confidence,
            "metadata": self.metadata,
            "metadata_valid": self.metadata_valid,
            "agent_type": self.agent_type.value if self.agent_type else None,
            "execution_result": self.execution_result,
            "execution_success": self.execution_success,
            "error_message": self.error_message,
            "user_response": self.user_response
        }
