"""
LLM Prompts Module
Author: Amit Bhagat
Purpose: Store and manage prompts for intent classification and metadata extraction
"""

# Intent Classification Prompt
INTENT_CLASSIFICATION_PROMPT = """You are an IT support assistant. Analyze the user request and identify the intent.

IMPORTANT: Be careful about keywords:
- "get details", "show info", "user information", "account info" = get_user_details
- "reset password", "change password", "new password" = password_reset  
- "unlock account", "unlock user" = account_unlock
- "grant access", "give access", "provide access" = grant_access
- "revoke access", "remove access" = revoke_access

User Request: {user_input}

Classify the intent as ONE of: get_user_details, password_reset, account_unlock, grant_access, revoke_access

Respond in VALID JSON format ONLY:
{{
    "intent": "<identified_intent>",
    "confidence": <confidence_score_0_to_1>,
    "explanation": "<brief_explanation>"
}}

Only respond with valid JSON, no additional text."""

# Metadata Extraction Prompt
METADATA_EXTRACTION_PROMPT = """You are an IT support assistant. Extract structured information from the user request.

User Request: {user_input}
Identified Intent: {intent}

Extract the following information if available in the request:
- username: User's username (AD format: firstname.lastname or email prefix)
- user_id: User's unique ID or Employee ID
- email: User's email address (format: user@domain.com)
- employee_number: Employee number if mentioned

IMPORTANT: 
- Extract email if it's in the request (format: something@domain.com)
- Extract username/first.last if it's in the request
- If email is present, extract the username part before @
- Set to null if not found in the request text

Respond in VALID JSON format ONLY:
{{
    "username": "<username_or_null>",
    "user_id": "<user_id_or_null>",
    "email": "<email_or_null>",
    "employee_number": "<employee_number_or_null>"
}}

Only respond with valid JSON, no additional text."""

# TODO: Add more prompts as needed for other intents and operations
