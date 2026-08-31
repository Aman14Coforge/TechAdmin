# """
# Metadata Extractor Module
# Author: Amit Bhagat
# Purpose: Extract relevant metadata from user input (username, email, etc.)
# """

# import json
# import os
# from typing import Dict, Any
# from langchain_ollama import ChatOllama
# from loguru import logger
# from App.intent.prompts import METADATA_EXTRACTION_PROMPT


# class MetadataExtractor:
#     """
#     Extracts structured metadata from user input using Ollama LLM.
#     Extracts: username, user_id, email, employee_number
#     """
    
#     def __init__(self, model_name: str = None, ollama_host: str = None):
#         """
#         Initialize the Metadata Extractor with Ollama LLM.
        
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
#                 temperature=0.1  # Very low temperature for precise extraction
#             )
#             logger.info(f"MetadataExtractor initialized - Model: {self.model_name}, Host: {self.ollama_host}")
#         except Exception as e:
#             logger.error(f"Failed to initialize ChatOllama: {str(e)}")
#             self.llm = None
    
#     def extract(self, user_input: str, intent: str) -> Dict[str, Any]:
#         """
#         Extract metadata from user input based on intent using Ollama LLM.
        
#         Args:
#             user_input: The user's request text
#             intent: The identified intent type
            
#         Returns:
#             Dict containing extracted metadata:
#             - username: User's username (AD/AAD format: firstname.lastname)
#             - user_id: User's ID
#             - email: User's email address
#             - employee_number: Employee number if available
#         """
#         logger.info(f"Extracting metadata for intent '{intent}' from: {user_input}")
        
#         if not self.llm:
#             logger.error("LLM not initialized")
#             return {
#                 "username": None,
#                 "user_id": None,
#                 "email": None,
#                 "employee_number": None
#             }
        
#         try:
#             # Build the prompt with user input and intent
#             prompt = METADATA_EXTRACTION_PROMPT.format(
#                 user_input=user_input,
#                 intent=intent
#             )
            
#             logger.debug(f"Sending metadata extraction prompt to Ollama...")
            
#             # Call Ollama LLM via ChatOllama
#             response = self.llm.invoke(prompt)
#             response_text = response.content.strip()
            
#             logger.debug(f"Raw LLM response: {response_text}")
            
#             # Parse JSON response from LLM
#             metadata = json.loads(response_text)
            
#             logger.info(f"Extracted metadata: {metadata}")
#             return metadata
            
#         except json.JSONDecodeError as e:
#             logger.error(f"Failed to parse JSON response: {str(e)}")
#             logger.error(f"LLM returned: {response_text if 'response_text' in locals() else 'No response'}")
            
#             # Fallback: return empty metadata
#             return {
#                 "username": None,
#                 "user_id": None,
#                 "email": None,
#                 "employee_number": None
#             }
            
#         except Exception as e:
#             logger.error(f"Error during extraction: {str(e)}", exc_info=True)
#             return {
#                 "username": None,
#                 "user_id": None,
#                 "email": None,
#                 "employee_number": None
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
        
#         # For password_reset, username is mandatory
#         if intent == "password_reset":
#             if not metadata.get("username"):
#                 msg = "Username is required for password reset"
#                 logger.warning(msg)
#                 return False, msg
        
#         # For get_user_details, username or email is mandatory
#         if intent == "get_user_details":
#             if not metadata.get("username") and not metadata.get("email"):
#                 msg = "Username or email is required to get user details"
#                 logger.warning(msg)
#                 return False, msg
        
#         logger.info(f"Metadata validation passed for intent '{intent}'")
#         return True, "Metadata is valid"



"""
Metadata Extractor Module
Author: Amit Bhagat
Purpose: Extract relevant metadata from user input (username, email, etc.)

Sends the user request to Ollama, parses the JSON reply, and validates it with the
UserMetadata Pydantic model so that missing fields come back as None rather than as
the text "null". Also validates that the fields required by the intent are present.
"""

from typing import Dict, Any
from loguru import logger
from App.intent.base import create_llm, parse_json_response
from App.intent.prompts import METADATA_EXTRACTION_PROMPT
from App.intent.schemas import UserMetadata, coerce_intent
from App.intent.schemas import validate_metadata as validate_intent_metadata


class MetadataExtractor:
    """
    Extracts structured metadata from user input using Ollama LLM.
    Extracts: username, user_id, email, employee_number
    """

    def __init__(self, model_name: str = None, ollama_host: str = None):
        """
        Initialize the Metadata Extractor with Ollama LLM.

        Args:
            model_name: Name of the Ollama model to use
            ollama_host: Ollama server URL
        """
        # Temperature 0 for precise, repeatable extraction.
        self.llm = create_llm(model_name, ollama_host, temperature=0.0)

    def extract(self, user_input: str, intent: str) -> Dict[str, Any]:
        """
        Extract metadata from user input based on intent using Ollama LLM.

        Args:
            user_input: The user's request text
            intent: The identified intent type

        Returns:
            Dict containing extracted metadata:
            - username: User's username (AD/AAD format: firstname.lastname)
            - user_id: User's ID
            - email: User's email address
            - employee_number: Employee number if available
        """
        logger.info(f"Extracting metadata for intent '{intent}' from: {user_input}")

        if not self.llm:
            logger.error("LLM not initialized")
            return UserMetadata().to_dict()

        try:
            prompt = METADATA_EXTRACTION_PROMPT.format(
                user_input=user_input,
                intent=coerce_intent(intent).value
            )

            logger.debug("Sending metadata extraction prompt to Ollama...")
            response = self.llm.invoke(prompt)
            response_text = response.content.strip()
            logger.debug(f"Raw LLM response: {response_text}")

            parsed = parse_json_response(response_text)

            if parsed is None:
                logger.error("Could not parse metadata from LLM response")
                return UserMetadata().to_dict()

            # Pydantic cleans up "null"/"N/A" style values into real None.
            metadata = UserMetadata(**parsed)

            logger.info(f"Extracted metadata: {metadata.to_dict()}")
            return metadata.to_dict()

        except Exception as e:
            logger.error(f"Error during extraction: {str(e)}", exc_info=True)
            return UserMetadata().to_dict()

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
