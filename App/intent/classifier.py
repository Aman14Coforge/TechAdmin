# """
# Intent Classifier Module
# Author: Amit Bhagat
# Purpose: Identify the type of user request (e.g., password_reset, account_unlock)
# """

# import json
# import os
# from typing import Dict, Any
# from langchain_ollama import ChatOllama
# from loguru import logger
# from App.intent.prompts import INTENT_CLASSIFICATION_PROMPT


# class IntentClassifier:
#     """
#     Classifies user input to identify the intent using Ollama LLM.
#     Supported intents: password_reset, account_unlock, grant_access, get_user_details
#     """
    
#     def __init__(self, model_name: str = None, ollama_host: str = None):
#         """
#         Initialize the Intent Classifier with Ollama LLM.
        
#         Args:
#             model_name: Name of the Ollama model to use
#             ollama_host: Ollama server URL
#         """
#         self.model_name = model_name or os.getenv("MODEL_NAME", "qwen3:14b")
#         self.ollama_host = ollama_host or os.getenv("OLLAMA_HOST", "http://localhost:11434")
        
#         try:
#             self.llm = ChatOllama(
#                 model=self.model_name,
#                 base_url=self.ollama_host,
#                 temperature=0.3  # Lower temperature for consistent classification
#             )
#             logger.info(f"IntentClassifier initialized - Model: {self.model_name}, Host: {self.ollama_host}")
#         except Exception as e:
#             logger.error(f"Failed to initialize ChatOllama: {str(e)}")
#             self.llm = None
    
#     def classify(self, user_input: str) -> Dict[str, Any]:
#         """
#         Classify the intent from user input using Ollama LLM.
        
#         Args:
#             user_input: The user's request text
            
#         Returns:
#             Dict containing:
#             - intent: Identified intent type
#             - confidence: Confidence score (0-1)
#             - explanation: Why this intent was chosen
#         """
#         logger.info(f"Classifying intent for input: {user_input}")
        
#         if not self.llm:
#             logger.error("LLM not initialized")
#             return {
#                 "intent": "unknown",
#                 "confidence": 0.0,
#                 "explanation": "LLM not available"
#             }
        
#         try:
#             # Build the prompt with user input
#             prompt = INTENT_CLASSIFICATION_PROMPT.format(user_input=user_input)
            
#             logger.debug(f"Sending prompt to Ollama...")
            
#             # Call Ollama LLM via ChatOllama
#             response = self.llm.invoke(prompt)
#             response_text = response.content.strip()
            
#             logger.debug(f"Raw LLM response: {response_text}")
            
#             # Parse JSON response from LLM
#             result = json.loads(response_text)
            
#             logger.info(f"Classification result: {result}")
#             return result
            
#         except json.JSONDecodeError as e:
#             logger.error(f"Failed to parse JSON response: {str(e)}")
#             logger.error(f"LLM returned: {response_text if 'response_text' in locals() else 'No response'}")
            
#             # Fallback: try to extract intent from response text
#             response_lower = response_text.lower() if 'response_text' in locals() else ""
#             if "details" in response_lower or "information" in response_lower:
#                 intent = "get_user_details"
#             elif "password" in response_lower and "reset" in response_lower:
#                 intent = "password_reset"
#             elif "unlock" in response_lower:
#                 intent = "account_unlock"
#             elif "access" in response_lower and "grant" in response_lower:
#                 intent = "grant_access"
#             else:
#                 intent = "unknown"
            
#             return {
#                 "intent": intent,
#                 "confidence": 0.5,
#                 "explanation": "Parsed from LLM response (JSON parse failed)"
#             }
            
#         except Exception as e:
#             logger.error(f"Error during classification: {str(e)}", exc_info=True)
#             return {
#                 "intent": "unknown",
#                 "confidence": 0.0,
#                 "explanation": f"Classification error: {str(e)}"
#             }
    
#     def get_supported_intents(self) -> list:
#         """Get list of supported intents."""
#         return [
#             "password_reset",
#             "account_unlock",
#             "grant_access",
#             "revoke_access",
#             "get_user_details"
#         ]


"""
Intent Classifier Module
Author: Amit Bhagat
Purpose: Identify the type of user request (e.g., password_reset, account_unlock)

Sends the user request to Ollama, parses the JSON reply, and validates it with the
IntentResult Pydantic model so the returned intent is always a supported value.
If the LLM reply cannot be parsed, a simple keyword match on the user request is used.
"""

from typing import Dict, Any
from loguru import logger
from App.intent.base import create_llm, parse_json_response
from App.intent.prompts import INTENT_CLASSIFICATION_PROMPT
from App.intent.schemas import IntentResult, SupportedIntent


# Keyword fallback rules, checked in order. More specific phrases come first.
KEYWORD_RULES = [
    (SupportedIntent.REVOKE_ACCESS, ["revoke access", "remove access", "revoke"]),
    (SupportedIntent.GRANT_ACCESS, ["grant access", "give access", "provide access"]),
    (SupportedIntent.ACCOUNT_UNLOCK, ["unlock", "locked out", "account locked"]),
    (SupportedIntent.PASSWORD_RESET, ["reset password", "password reset", "change password"]),
    (SupportedIntent.GET_USER_DETAILS, ["get details", "user details", "show info", "user information", "account info"]),
]


class IntentClassifier:
    """
    Classifies user input to identify the intent using Ollama LLM.
    Supported intents: password_reset, account_unlock, grant_access, revoke_access,
    get_user_details
    """

    def __init__(self, model_name: str = None, ollama_host: str = None):
        """
        Initialize the Intent Classifier with Ollama LLM.

        Args:
            model_name: Name of the Ollama model to use
            ollama_host: Ollama server URL
        """
        # Temperature 0 keeps classification consistent across runs.
        self.llm = create_llm(model_name, ollama_host, temperature=0.0)

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
            return IntentResult(explanation="LLM not available").to_dict()

        try:
            prompt = INTENT_CLASSIFICATION_PROMPT.format(user_input=user_input)

            logger.debug("Sending prompt to Ollama...")
            response = self.llm.invoke(prompt)
            response_text = response.content.strip()
            logger.debug(f"Raw LLM response: {response_text}")

            parsed = parse_json_response(response_text)

            if parsed is None:
                # Could not read the LLM reply, so fall back to keyword matching.
                return self._keyword_fallback(user_input)

            # Pydantic validates the intent value and the confidence score.
            result = IntentResult(**parsed)

            logger.info(f"Classification result: {result.to_dict()}")
            return result.to_dict()

        except Exception as e:
            logger.error(f"Error during classification: {str(e)}", exc_info=True)
            return IntentResult(explanation=f"Classification error: {str(e)}").to_dict()

    def _keyword_fallback(self, user_input: str) -> Dict[str, Any]:
        """
        Simple keyword match on the user request, used when the LLM reply is unusable.

        Args:
            user_input: The user's request text

        Returns:
            Dict with intent, confidence and explanation.
        """
        text = (user_input or "").lower()

        for intent, keywords in KEYWORD_RULES:
            if any(keyword in text for keyword in keywords):
                logger.info(f"Keyword fallback matched intent '{intent.value}'")
                return IntentResult(
                    intent=intent,
                    confidence=0.5,
                    explanation="Matched by keyword fallback (JSON parse failed)",
                ).to_dict()

        logger.info("Keyword fallback found no match")
        return IntentResult(
            explanation="Could not determine intent (JSON parse failed)"
        ).to_dict()

    def get_supported_intents(self) -> list:
        """Get list of supported intents."""
        return [
            "password_reset",
            "account_unlock",
            "grant_access",
            "revoke_access",
            "get_user_details"
        ]
