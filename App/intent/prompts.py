# """
# LLM Prompts Module
# Author: Amit Bhagat
# Purpose: Store and manage prompts for intent classification and metadata extraction
# """

# # Intent Classification Prompt
# INTENT_CLASSIFICATION_PROMPT = """You are an IT support assistant. Analyze the user request and identify the intent.

# IMPORTANT: Be careful about keywords:
# - "get details", "show info", "user information", "account info" = get_user_details
# - "reset password", "change password", "new password" = password_reset  
# - "unlock account", "unlock user" = account_unlock
# - "grant access", "give access", "provide access" = grant_access
# - "revoke access", "remove access" = revoke_access

# User Request: {user_input}

# Classify the intent as ONE of: get_user_details, password_reset, account_unlock, grant_access, revoke_access

# Respond in VALID JSON format ONLY:
# {{
#     "intent": "<identified_intent>",
#     "confidence": <confidence_score_0_to_1>,
#     "explanation": "<brief_explanation>"
# }}

# Only respond with valid JSON, no additional text."""

# # Metadata Extraction Prompt
# METADATA_EXTRACTION_PROMPT = """You are an IT support assistant. Extract structured information from the user request.

# User Request: {user_input}
# Identified Intent: {intent}

# Extract the following information if available in the request:
# - username: User's username (AD format: firstname.lastname or email prefix)
# - user_id: User's unique ID or Employee ID
# - email: User's email address (format: user@domain.com)
# - employee_number: Employee number if mentioned

# IMPORTANT: 
# - Extract email if it's in the request (format: something@domain.com)
# - Extract username/first.last if it's in the request
# - If email is present, extract the username part before @
# - Set to null if not found in the request text

# Respond in VALID JSON format ONLY:
# {{
#     "username": "<username_or_null>",
#     "user_id": "<user_id_or_null>",
#     "email": "<email_or_null>",
#     "employee_number": "<employee_number_or_null>"
# }}

# Only respond with valid JSON, no additional text."""

# # TODO: Add more prompts as needed for other intents and operations


"""
LLM Prompts Module
Author: Amit Bhagat
Purpose: Store and manage prompts for intent classification and metadata extraction.

Three prompts are defined:
  - INTENT_CLASSIFICATION_PROMPT : intent only
  - METADATA_EXTRACTION_PROMPT   : metadata only, given a known intent
  - UNIFIED_EXTRACTION_PROMPT    : both in a single call

The intent list and the extraction rules are kept as shared blocks so that a rule
only has to be edited in one place.
"""

# Shared intent definitions used by the classification and unified prompts.
_INTENT_RULES = """Supported intents:
- get_user_details : "get details", "show info", "user information", "account info", "look up user"
- password_reset   : "reset password", "change password", "new password", "forgot password"
- account_unlock   : "unlock account", "unlock user", "account is locked", "locked out"
- grant_access     : "grant access", "give access", "provide access", "add to group"
- revoke_access    : "revoke access", "remove access", "take away access", "remove from group"
- unknown          : anything else, such as hardware faults, network issues or software installs

Rules:
- "remove access" and "revoke" are always revoke_access, never grant_access.
- A request that only asks to SEE information is get_user_details, even if it mentions
  a password or a locked account.
- If the request does not match any supported intent, answer "unknown"."""

# Shared metadata rules used by the extraction and unified prompts.
_METADATA_RULES = """Fields to extract:
- username        : AD username, usually first.last. If only an email is given, use the part before the @.
- user_id         : user or employee ID, only if explicitly stated
- email           : full address in the form something@domain.com
- employee_number : employee number, only if explicitly stated

Rules:
- Copy values exactly as they appear in the request. Do not guess or invent them.
- If a field is not present in the request, use the JSON value null (not the text "null")."""

# Shared output rules.
_OUTPUT_RULES = """Output rules:
- Respond with a single JSON object and nothing else.
- No markdown, no explanation before or after, no <think> block.
- confidence must be a number between 0 and 1, not a string."""


INTENT_CLASSIFICATION_PROMPT = """You are an IT support assistant. Identify the intent of the user request.

""" + _INTENT_RULES + """

""" + _OUTPUT_RULES + """

Respond in this JSON format:
{{
    "intent": "<one of: get_user_details, password_reset, account_unlock, grant_access, revoke_access, unknown>",
    "confidence": 0.0,
    "explanation": "<brief explanation>"
}}

Examples:
Request: "Please reset the password for john.doe"
{{"intent": "password_reset", "confidence": 0.97, "explanation": "Asks to reset a password."}}

Request: "remove sarah.lee's access to the finance share"
{{"intent": "revoke_access", "confidence": 0.95, "explanation": "Asks to remove existing access."}}

Request: "my laptop will not turn on"
{{"intent": "unknown", "confidence": 0.9, "explanation": "Hardware issue, not an identity request."}}

User Request: {user_input}

JSON response:"""


METADATA_EXTRACTION_PROMPT = """You are an IT support assistant. Extract structured information from the user request.

Identified Intent: {intent}

""" + _METADATA_RULES + """

""" + _OUTPUT_RULES + """

Respond in this JSON format:
{{
    "username": null,
    "user_id": null,
    "email": null,
    "employee_number": null
}}

Examples:
Request: "Get details for derhant@coforge.com"
{{"username": "derhant", "user_id": null, "email": "derhant@coforge.com", "employee_number": null}}

Request: "unlock the account for john.doe, employee 44821"
{{"username": "john.doe", "user_id": null, "email": null, "employee_number": "44821"}}

Request: "please reset the password for the new joiner"
{{"username": null, "user_id": null, "email": null, "employee_number": null}}

User Request: {user_input}

JSON response:"""


UNIFIED_EXTRACTION_PROMPT = """You are an IT support assistant. Identify the intent of the user request
and extract the user information from it, in a single response.

""" + _INTENT_RULES + """

""" + _METADATA_RULES + """

""" + _OUTPUT_RULES + """

Respond in this JSON format:
{{
    "intent": "<one of: get_user_details, password_reset, account_unlock, grant_access, revoke_access, unknown>",
    "confidence": 0.0,
    "explanation": "<brief explanation>",
    "metadata": {{
        "username": null,
        "user_id": null,
        "email": null,
        "employee_number": null
    }}
}}

Examples:
Request: "Get details for derhant@coforge.com"
{{"intent": "get_user_details", "confidence": 0.96, "explanation": "Asks for a user profile.",
  "metadata": {{"username": "derhant", "user_id": null, "email": "derhant@coforge.com", "employee_number": null}}}}

Request: "Please reset the password for john.doe, employee 44821"
{{"intent": "password_reset", "confidence": 0.98, "explanation": "Asks to reset a password.",
  "metadata": {{"username": "john.doe", "user_id": null, "email": null, "employee_number": "44821"}}}}

Request: "remove sarah.lee from the finance share"
{{"intent": "revoke_access", "confidence": 0.93, "explanation": "Asks to remove existing access.",
  "metadata": {{"username": "sarah.lee", "user_id": null, "email": null, "employee_number": null}}}}

Request: "the office wifi keeps dropping"
{{"intent": "unknown", "confidence": 0.91, "explanation": "Network issue, not an identity request.",
  "metadata": {{"username": null, "user_id": null, "email": null, "employee_number": null}}}}

User Request: {user_input}

JSON response:"""
