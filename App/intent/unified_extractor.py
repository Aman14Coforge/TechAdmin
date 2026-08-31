# """
# Unified Intent & Metadata Extractor
# Author: Amit Bhagat
# Purpose: Extract intent AND metadata in a single Ollama LLM call
# Optimization: Reduces 2 API calls to 1 for better performance
# """

# import json
# import os
# from typing import Dict, Any
# from langchain_ollama import ChatOllama
# from loguru import logger


# class UnifiedIntentMetadataExtractor:
#     """
#     Extracts both intent AND metadata in a single LLM call.
#     Much faster than making 2 separate calls.
#     """
    
#     def __init__(self, model_name: str = None, ollama_host: str = None):
#         """
#         Initialize the unified extractor with Ollama LLM.
        
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
#                 temperature=0.2  # Low temp for consistent extraction
#             )
#             logger.info(f"UnifiedIntentMetadataExtractor initialized - Model: {self.model_name}")
#         except Exception as e:
#             logger.error(f"Failed to initialize ChatOllama: {str(e)}")
#             self.llm = None
    
#     def extract_all(self, user_input: str) -> Dict[str, Any]:
#         """
#         Extract intent AND metadata in ONE LLM call.
        
#         Args:
#             user_input: The user's request text
            
#         Returns:
#             Dict containing:
#             - intent: Identified intent type
#             - confidence: Confidence score (0-1)
#             - explanation: Why this intent was chosen
#             - metadata: Dict with username, email, user_id, employee_number
#             - success: Whether extraction succeeded
#         """
#         logger.info(f"Extracting intent + metadata in single call for: {user_input}")
        
#         if not self.llm:
#             logger.error("LLM not initialized")
#             return {
#                 "success": False,
#                 "intent": "unknown",
#                 "confidence": 0.0,
#                 "explanation": "LLM not available",
#                 "metadata": {"username": None, "email": None, "user_id": None, "employee_number": None}
#             }
        
#         try:
#             # Single unified prompt for both intent and metadata extraction
#             prompt = f"""You are an IT support assistant. Analyze the user request and extract BOTH intent and metadata.

# IMPORTANT: Be careful about keywords:
# - "get details", "show info", "user information", "account info" = get_user_details
# - "reset password", "change password", "new password" = password_reset  
# - "unlock account", "unlock user" = account_unlock
# - "grant access", "give access", "provide access" = grant_access
# - "revoke access", "remove access" = revoke_access

# User Request: {user_input}

# Extract and respond in VALID JSON format ONLY:
# {{
#     "intent": "<identified_intent: one of get_user_details, password_reset, account_unlock, grant_access, revoke_access>",
#     "confidence": <confidence_score_0_to_1>,
#     "explanation": "<brief_explanation>",
#     "metadata": {{
#         "username": "<username_or_null>",
#         "user_id": "<user_id_or_null>",
#         "email": "<email_or_null>",
#         "employee_number": "<employee_number_or_null>"
#     }}
# }}

# IMPORTANT for metadata:
# - Extract email if it's in the request (format: something@domain.com)
# - Extract username/first.last if it's in the request
# - If email is present, extract the username part before @
# - Set to null if not found in the request text

# Only respond with valid JSON, no additional text."""
            
#             logger.debug(f"Sending unified prompt to Ollama...")
            
#             # Single LLM call for both intent and metadata
#             response = self.llm.invoke(prompt)
#             response_text = response.content.strip()
            
#             logger.debug(f"Raw LLM response: {response_text}")
            
#             # Parse JSON response
#             result = json.loads(response_text)
#             result["success"] = True
            
#             logger.info(f"Extraction result - Intent: {result.get('intent')}, Metadata: {result.get('metadata')}")
#             return result
            
#         except json.JSONDecodeError as e:
#             logger.error(f"Failed to parse JSON response: {str(e)}")
#             logger.error(f"LLM returned: {response_text if 'response_text' in locals() else 'N/A'}")
            
#             return {
#                 "success": False,
#                 "intent": "unknown",
#                 "confidence": 0.0,
#                 "explanation": "Failed to parse LLM response",
#                 "metadata": {"username": None, "email": None, "user_id": None, "employee_number": None}
#             }
            
#         except Exception as e:
#             logger.error(f"Error during extraction: {str(e)}", exc_info=True)
#             return {
#                 "success": False,
#                 "intent": "unknown",
#                 "confidence": 0.0,
#                 "explanation": f"Extraction error: {str(e)}",
#                 "metadata": {"username": None, "email": None, "user_id": None, "employee_number": None}
#             }
    
#     def validate_metadata(self, metadata: Dict[str, Any], intent: str) -> tuple:
#         """
#         Validate that all required metadata for the intent is present.
        
#         Args:
#             metadata: Extracted metadata dictionary
#             intent: The intent type
            
#         Returns:
#             Tuple of (is_valid, error_message)
#         """
#         logger.info(f"Validating metadata for intent '{intent}'")
        
#         if intent == "password_reset":
#             if not metadata.get("username"):
#                 msg = "Username is required for password reset"
#                 logger.warning(msg)
#                 return False, msg
        
#         if intent == "get_user_details":
#             if not metadata.get("username") and not metadata.get("email"):
#                 msg = "Username or email is required to get user details"
#                 logger.warning(msg)
#                 return False, msg
        
#         logger.info(f"Metadata validation passed for intent '{intent}'")
#         return True, "Metadata is valid"


"""
Unified Intent & Metadata Extractor
Author: Amit Bhagat
Purpose: Extract intent AND metadata in a single Ollama LLM call
Optimization: Reduces 2 API calls to 1 for better performance

This is the extractor used by the workflow. The reply is validated with the
ExtractionResult Pydantic model, so the intent is always a supported value, the
confidence is always a number, and the metadata dictionary is always present.
"""

from typing import Dict, Any
from loguru import logger
from App.intent.base import create_llm, parse_json_response
from App.intent.prompts import UNIFIED_EXTRACTION_PROMPT
from App.intent.schemas import ExtractionResult, SupportedIntent
from App.intent.schemas import validate_metadata as validate_intent_metadata


class UnifiedIntentMetadataExtractor:
    """
    Extracts both intent AND metadata in a single LLM call.
    Much faster than making 2 separate calls.
    """

    def __init__(self, model_name: str = None, ollama_host: str = None):
        """
        Initialize the unified extractor with Ollama LLM.

        Args:
            model_name: Name of the Ollama model to use
            ollama_host: Ollama server URL
        """
        # Temperature 0 for consistent extraction across runs.
        self.llm = create_llm(model_name, ollama_host, temperature=0.0)

    def extract_all(self, user_input: str) -> Dict[str, Any]:
        """
        Extract intent AND metadata in ONE LLM call.

        Args:
            user_input: The user's request text

        Returns:
            Dict containing:
            - intent: Identified intent type
            - confidence: Confidence score (0-1)
            - explanation: Why this intent was chosen
            - metadata: Dict with username, email, user_id, employee_number
            - success: Whether extraction succeeded
        """
        logger.info(f"Extracting intent + metadata in single call for: {user_input}")

        if not self.llm:
            logger.error("LLM not initialized")
            return ExtractionResult(explanation="LLM not available").to_dict()

        try:
            prompt = UNIFIED_EXTRACTION_PROMPT.format(user_input=user_input)

            logger.debug("Sending unified prompt to Ollama...")
            response = self.llm.invoke(prompt)
            response_text = response.content.strip()
            logger.debug(f"Raw LLM response: {response_text}")

            parsed = parse_json_response(response_text)

            if parsed is None:
                logger.error("Could not parse LLM response")
                return ExtractionResult(
                    explanation="Failed to parse LLM response"
                ).to_dict()

            # Pydantic validates the intent, the confidence and the metadata shape.
            result = ExtractionResult(**parsed)

            # An out-of-scope request is a valid answer but not an actionable one,
            # so it is not passed on to the router.
            result.success = result.intent is not SupportedIntent.UNKNOWN

            logger.info(
                f"Extraction result - Intent: {result.intent.value}, "
                f"Metadata: {result.metadata.to_dict()}"
            )
            return result.to_dict()

        except Exception as e:
            logger.error(f"Error during extraction: {str(e)}", exc_info=True)
            return ExtractionResult(
                explanation=f"Extraction error: {str(e)}"
            ).to_dict()

    def validate_metadata(self, metadata: Dict[str, Any], intent: str) -> tuple:
        """
        Validate that all required metadata for the intent is present.

        Args:
            metadata: Extracted metadata dictionary
            intent: The intent type

        Returns:
            Tuple of (is_valid, error_message)
        """
        return validate_intent_metadata(metadata, intent)
