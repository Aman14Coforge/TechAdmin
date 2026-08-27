"""
Intent Classifier Module
Author: Amit Bhagat
Purpose: Identify the type of user request (e.g., password_reset, account_unlock)
"""

import json
import os
from typing import Dict, Any
from langchain_ollama import ChatOllama
from loguru import logger
from App.intent.prompts import INTENT_CLASSIFICATION_PROMPT


class IntentClassifier:
    """
    Classifies user input to identify the intent using Ollama LLM.
    Supported intents: password_reset, account_unlock, grant_access, get_user_details
    """
    
    def __init__(self, model_name: str = None, ollama_host: str = None):
        """
        Initialize the Intent Classifier with Ollama LLM.
        
        Args:
            model_name: Name of the Ollama model to use
            ollama_host: Ollama server URL
        """
        self.model_name = model_name or os.getenv("MODEL_NAME", "qwen3:14b")
        self.ollama_host = ollama_host or os.getenv("OLLAMA_HOST", "http://localhost:11434")
        
        try:
            self.llm = ChatOllama(
                model=self.model_name,
                base_url=self.ollama_host,
                temperature=0.3  # Lower temperature for consistent classification
            )
            logger.info(f"IntentClassifier initialized - Model: {self.model_name}, Host: {self.ollama_host}")
        except Exception as e:
            logger.error(f"Failed to initialize ChatOllama: {str(e)}")
            self.llm = None
    
    def classify(self, user_input: str) -> Dict[str, Any]:
        """
        Classify the intent from user input using Ollama LLM.
        
        Args:
            user_input: The user's request text
            
        Returns:
            Dict containing:
            - intent: Identified intent type
            - confidence: Confidence score (0-1)
            - explanation: Why this intent was chosen
        """
        logger.info(f"Classifying intent for input: {user_input}")
        
        if not self.llm:
            logger.error("LLM not initialized")
            return {
                "intent": "unknown",
                "confidence": 0.0,
                "explanation": "LLM not available"
            }
        
        try:
            # Build the prompt with user input
            prompt = INTENT_CLASSIFICATION_PROMPT.format(user_input=user_input)
            
            logger.debug(f"Sending prompt to Ollama...")
            
            # Call Ollama LLM via ChatOllama
            response = self.llm.invoke(prompt)
            response_text = response.content.strip()
            
            logger.debug(f"Raw LLM response: {response_text}")
            
            # Parse JSON response from LLM
            result = json.loads(response_text)
            
            logger.info(f"Classification result: {result}")
            return result
            
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse JSON response: {str(e)}")
            logger.error(f"LLM returned: {response_text if 'response_text' in locals() else 'No response'}")
            
            # Fallback: try to extract intent from response text
            response_lower = response_text.lower() if 'response_text' in locals() else ""
            if "details" in response_lower or "information" in response_lower:
                intent = "get_user_details"
            elif "password" in response_lower and "reset" in response_lower:
                intent = "password_reset"
            elif "unlock" in response_lower:
                intent = "account_unlock"
            elif "access" in response_lower and "grant" in response_lower:
                intent = "grant_access"
            else:
                intent = "unknown"
            
            return {
                "intent": intent,
                "confidence": 0.5,
                "explanation": "Parsed from LLM response (JSON parse failed)"
            }
            
        except Exception as e:
            logger.error(f"Error during classification: {str(e)}", exc_info=True)
            return {
                "intent": "unknown",
                "confidence": 0.0,
                "explanation": f"Classification error: {str(e)}"
            }
    
    def get_supported_intents(self) -> list:
        """Get list of supported intents."""
        return [
            "password_reset",
            "account_unlock",
            "grant_access",
            "revoke_access",
            "get_user_details"
        ]
