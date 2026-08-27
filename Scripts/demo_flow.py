"""
Complete Flow Demo - End-to-End Test
Author: Aman Gupta
Purpose: Test the entire workflow with real Graph API calls
Usage: python Scripts/demo_flow.py
"""

import sys
import os
import json
from pathlib import Path
from dotenv import load_dotenv
from loguru import logger

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Load environment variables
load_dotenv()

from App.intent.unified_extractor import UnifiedIntentMetadataExtractor
from App.workflow.router import AgentRouter
from App.agents.identity_agent import IdentityAgent
from App.workflow.formatter import ResponseFormatter
from App.utils.config import Logger, Config

# Setup logging
Logger.setup()


class DemoFlow:
    """Complete workflow demonstration."""
    
    def __init__(self):
        """Initialize components."""
        logger.info("=" * 80)
        logger.info("TechAdmin Demo Flow - Complete End-to-End Test")
        logger.info("=" * 80)
        
        # Use unified extractor instead of 2 separate calls
        self.extractor = UnifiedIntentMetadataExtractor()
        self.router = AgentRouter()
        self.identity_agent = IdentityAgent()
        self.formatter = ResponseFormatter()
    
    def execute_flow(self, user_input: str, request_id: str = None) -> dict:
        """
        Execute the complete workflow.
        
        Args:
            user_input: User's request
            request_id: Optional request ID
            
        Returns:
            Final response dict
        """
        if not request_id:
            import uuid
            request_id = f"demo_{uuid.uuid4().hex[:8]}"
        
        logger.info(f"\n{'='*80}")
        logger.info(f"REQUEST ID: {request_id}")
        logger.info(f"USER INPUT: {user_input}")
        logger.info(f"{'='*80}\n")
        
        try:
            # STEP 1 & 2 COMBINED: Intent Classification + Metadata Extraction in ONE call
            logger.info("STEP 1 & 2: Intent Classification + Metadata Extraction (Unified Call)")
            logger.info("-" * 40)
            
            extraction_result = self.extractor.extract_all(user_input)
            
            if not extraction_result.get("success"):
                logger.error(f"Extraction failed: {extraction_result.get('explanation')}")
                return {
                    "success": False,
                    "request_id": request_id,
                    "error": extraction_result.get('explanation'),
                    "message": "Failed to process request"
                }
            
            intent = extraction_result.get("intent")
            confidence = extraction_result.get("confidence", 0)
            metadata = extraction_result.get("metadata", {})
            
            logger.info(f"Intent: {intent}")
            logger.info(f"Confidence: {confidence}")
            logger.info(f"Metadata: {json.dumps(metadata, indent=2)}")
            
            if confidence < 0.7:
                logger.warning(f"Low confidence ({confidence}) for intent classification")
                return {
                    "success": False,
                    "request_id": request_id,
                    "error": f"Could not confidently determine intent (confidence: {confidence})",
                    "message": "Unable to process request due to low confidence in intent classification"
                }
            
            # Validate metadata
            is_valid, validation_msg = self.extractor.validate_metadata(metadata, intent)
            if not is_valid:
                logger.error(f"Metadata validation failed: {validation_msg}")
                return {
                    "success": False,
                    "request_id": request_id,
                    "intent": intent,
                    "error": validation_msg,
                    "message": f"Invalid metadata: {validation_msg}"
                }
            
            # STEP 3: Router
            logger.info("\nSTEP 3: Agent Routing")
            logger.info("-" * 40)
            routing_info = self.router.route(intent, metadata)
            logger.info(f"Routing Info: {json.dumps(routing_info, indent=2)}")
            
            agent_type = routing_info.get("agent_type")
            
            # STEP 4: Agent Execution
            logger.info(f"\nSTEP 4: {agent_type.upper()} Agent Execution")
            logger.info("-" * 40)
            
            if agent_type == "identity":
                agent_result = self.identity_agent.execute(intent, metadata)
            else:
                return {
                    "success": False,
                    "request_id": request_id,
                    "intent": intent,
                    "error": f"Unsupported agent type: {agent_type}",
                    "message": f"No agent available for {agent_type}"
                }
            
            logger.info(f"Agent Result: {json.dumps(agent_result, indent=2, default=str)}")
            
            # STEP 5: Response Formatting
            logger.info("\nSTEP 5: Response Formatting")
            logger.info("-" * 40)
            
            if intent == "get_user_details":
                user_data = agent_result.get("result")
                if agent_result.get("success") and user_data:
                    formatted_response = f"""
✅ User Details Retrieved Successfully

User ID: {user_data.get('id')}
Display Name: {user_data.get('displayName')}
Email: {user_data.get('userPrincipalName')}
Account Enabled: {user_data.get('accountEnabled')}
User Type: {user_data.get('userType')}
AD Sync Enabled: {user_data.get('onPremisesSyncEnabled')}
Mail: {user_data.get('mail')}
"""
                else:
                    formatted_response = self.formatter.format_error_response(
                        agent_result.get("message"),
                        agent_result.get("error")
                    )
            elif intent == "password_reset":
                if agent_result.get("success"):
                    formatted_response = self.formatter.format_password_reset_response(
                        True,
                        metadata.get("username"),
                        agent_result.get("result")
                    )
                else:
                    formatted_response = self.formatter.format_password_reset_response(
                        False,
                        metadata.get("username"),
                        None,
                        agent_result.get("error")
                    )
            else:
                formatted_response = agent_result.get("message")
            
            logger.info(f"Formatted Response:\n{formatted_response}")
            
            # FINAL RESPONSE
            final_response = {
                "success": agent_result.get("success", False),
                "request_id": request_id,
                "intent": intent,
                "message": formatted_response,
                "metadata": metadata,
                "result": agent_result.get("result"),
                "error": agent_result.get("error")
            }
            
            return final_response
            
        except Exception as e:
            logger.error(f"Unexpected error in flow: {str(e)}", exc_info=True)
            return {
                "success": False,
                "request_id": request_id,
                "error": str(e),
                "message": "An unexpected error occurred during processing"
            }


def print_response(response: dict):
    """Pretty print the response."""
    print("\n" + "=" * 80)
    print("FINAL RESPONSE")
    print("=" * 80)
    print(json.dumps(response, indent=2, default=str))
    print("=" * 80 + "\n")


def main():
    """Run demo flow tests."""
    demo = DemoFlow()
    
    # Test cases
    test_cases = [
        "Get details for derhant@coforge.com",
        "Find user details for derhant",
        "Reset password for aman.gupta",
        "What is my account status"
    ]
    
    print("\n" + "=" * 80)
    print("TECHADMIN DEMO FLOW - INTERACTIVE TEST")
    print("=" * 80)
    print("\nEnter user request (or press Enter for predefined tests):")
    print("Examples:")
    for i, case in enumerate(test_cases, 1):
        print(f"  {i}. {case}")
    
    user_input = input("\nYour request (or number 1-4 for examples): ").strip()
    
    if user_input.isdigit() and 1 <= int(user_input) <= len(test_cases):
        user_input = test_cases[int(user_input) - 1]
    elif not user_input:
        user_input = test_cases[0]  # Default to first test
    
    # Execute flow
    response = demo.execute_flow(user_input)
    
    # Print response
    print_response(response)
    
    # Print summary
    logger.info("\n" + "=" * 80)
    logger.info("EXECUTION SUMMARY")
    logger.info("=" * 80)
    logger.info(f"Success: {response.get('success')}")
    logger.info(f"Intent: {response.get('intent')}")
    logger.info(f"Request ID: {response.get('request_id')}")
    if response.get('error'):
        logger.info(f"Error: {response.get('error')}")
    logger.info("=" * 80 + "\n")


if __name__ == "__main__":
    # Validate configuration
    if not Config.validate():
        logger.error("Configuration validation failed!")
        print("\n❌ Configuration Error!")
        print("\nPlease ensure the following environment variables are set in .env:")
        print("  - OLLAMA_HOST (e.g., http://localhost:11434)")
        print("  - MODEL_NAME (e.g., qwen3:14b)")
        print("  - GRAPH_CLIENT_ID")
        print("  - GRAPH_CLIENT_SECRET")
        print("  - GRAPH_TENANT_ID")
        sys.exit(1)
    
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nDemo interrupted by user.")
        sys.exit(0)
