# """
# API Request/Response Schemas
# Author: Roshan
# Purpose: Define Pydantic models for API validation
# """

# from pydantic import BaseModel, Field, validator
# from typing import Optional, Dict, Any
# from enum import Enum


# class IntentEnum(str, Enum):
#     """Supported intents."""
#     PASSWORD_RESET = "password_reset"
#     ACCOUNT_UNLOCK = "account_unlock"
#     GRANT_ACCESS = "grant_access"
#     REVOKE_ACCESS = "revoke_access"


# class UserRequestSchema(BaseModel):
#     """
#     Schema for incoming user request to the API.
    
#     Example:
#     {
#         "user_input": "Reset password for aman.gupta",
#         "request_id": "req_12345"
#     }
#     """
#     user_input: str = Field(..., min_length=1, description="User's request text")
#     request_id: Optional[str] = Field(
#         default=None, 
#         description="Unique request ID for tracking (auto-generated if not provided)"
#     )
    
#     @validator('user_input')
#     def validate_user_input(cls, v):
#         """Validate user input is not empty."""
#         if not v or len(v.strip()) == 0:
#             raise ValueError('User input cannot be empty')
#         return v


# class IntentResultSchema(BaseModel):
#     """Response schema for intent classification."""
#     intent: IntentEnum
#     confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score 0-1")
#     explanation: str = Field(..., description="Why this intent was chosen")


# class MetadataSchema(BaseModel):
#     """Extracted metadata from user input."""
#     username: Optional[str] = Field(None, description="User's username")
#     user_id: Optional[str] = Field(None, description="User's ID")
#     email: Optional[str] = Field(None, description="User's email address")
#     employee_number: Optional[str] = Field(None, description="Employee number")


# class OperationResultSchema(BaseModel):
#     """Result of an operation execution."""
#     success: bool = Field(..., description="Whether operation succeeded")
#     message: str = Field(..., description="User-friendly message")
#     result: Optional[Dict[str, Any]] = Field(None, description="Operation result details")
#     error: Optional[str] = Field(None, description="Error message if failed")


# class APIResponseSchema(BaseModel):
#     """
#     Final API response schema.
    
#     Example:
#     {
#         "success": true,
#         "request_id": "req_12345",
#         "intent": "password_reset",
#         "message": "Password reset completed successfully",
#         "metadata": {"username": "aman.gupta"},
#         "result": {
#             "user_id": "user123",
#             "status": "completed"
#         }
#     }
#     """
#     success: bool = Field(..., description="Whether the request was successful")
#     request_id: str = Field(..., description="Unique request ID for tracking")
#     intent: Optional[str] = Field(None, description="Identified intent")
#     message: str = Field(..., description="User-friendly response message")
#     metadata: Optional[MetadataSchema] = Field(None, description="Extracted metadata")
#     result: Optional[Dict[str, Any]] = Field(None, description="Operation result details")
#     error: Optional[str] = Field(None, description="Error message if failed")


# class APIErrorResponseSchema(BaseModel):
#     """Error response schema."""
#     success: bool = Field(False, description="Always false for errors")
#     request_id: Optional[str] = Field(None, description="Request ID if available")
#     error: str = Field(..., description="Error message")
#     details: Optional[str] = Field(None, description="Additional error details")

"""
API Request/Response Schemas
Author: Roshan
Purpose: Define Pydantic models for API validation
"""

from pydantic import BaseModel, Field, validator
from typing import Optional, Dict, Any
from enum import Enum


class IntentEnum(str, Enum):
    """Supported intents."""
    PASSWORD_RESET = "password_reset"
    ACCOUNT_UNLOCK = "account_unlock"
    GRANT_ACCESS = "grant_access"
    REVOKE_ACCESS = "revoke_access"


class UserRequestSchema(BaseModel):
    """
    Schema for incoming user request to the API.
    
    Example:
    {
        "user_input": "Reset password for aman.gupta",
        "request_id": "req_12345"
    }
    """
    user_input: str = Field(..., min_length=1, description="User's request text")
    request_id: Optional[str] = Field(
        default=None, 
        description="Unique request ID for tracking (auto-generated if not provided)"
    )
    
    @validator('user_input')
    def validate_user_input(cls, v):
        """Validate user input is not empty."""
        if not v or len(v.strip()) == 0:
            raise ValueError('User input cannot be empty')
        return v


class IntentResultSchema(BaseModel):
    """Response schema for intent classification."""
    intent: IntentEnum
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score 0-1")
    explanation: str = Field(..., description="Why this intent was chosen")


class MetadataSchema(BaseModel):
    """Extracted metadata from user input."""
    username: Optional[str] = Field(None, description="User's username")
    user_id: Optional[str] = Field(None, description="User's ID")
    email: Optional[str] = Field(None, description="User's email address")
    employee_number: Optional[str] = Field(None, description="Employee number")


class OperationResultSchema(BaseModel):
    """Result of an operation execution."""
    success: bool = Field(..., description="Whether operation succeeded")
    message: str = Field(..., description="User-friendly message")
    result: Optional[Dict[str, Any]] = Field(None, description="Operation result details")
    error: Optional[str] = Field(None, description="Error message if failed")


class APIResponseSchema(BaseModel):
    """
    Final API response schema.
    
    Example:
    {
        "success": true,
        "request_id": "req_12345",
        "intent": "password_reset",
        "message": "Password reset completed successfully",
        "metadata": {"username": "aman.gupta"},
        "result": {
            "user_id": "user123",
            "status": "completed"
        }
    }
    """
    success: bool = Field(..., description="Whether the request was successful")
    request_id: str = Field(..., description="Unique request ID for tracking")
    intent: Optional[str] = Field(None, description="Identified intent")
    message: str = Field(..., description="User-friendly response message")
    metadata: Optional[MetadataSchema] = Field(None, description="Extracted metadata")
    result: Optional[Dict[str, Any]] = Field(None, description="Operation result details")
    error: Optional[str] = Field(None, description="Error message if failed")


class APIErrorResponseSchema(BaseModel):
    """Error response schema."""
    success: bool = Field(False, description="Always false for errors")
    request_id: Optional[str] = Field(None, description="Request ID if available")
    error: str = Field(..., description="Error message")
    details: Optional[str] = Field(None, description="Additional error details")


# --- ADDED FOR PASSWORD ENHANCEMENTS (Amit Bhagat) ---
class PasswordResetResponseSchema(BaseModel):
    """
    Response for POST /reset-password.

    The original password is deliberately absent. masked_password is what the
    UI shows, and password_token is the opaque handle the download and email
    endpoints exchange for the real value server-side.
    """

    status: str = Field(default="success", description="success or error")
    username: str = Field(description="The account that was reset")
    masked_password: str = Field(description="Masked form, e.g. Temp****45")
    password_token: str = Field(description="Opaque handle for download and email")
    manager_name: str = Field(default="Not Available")
    manager_email: str = Field(default="Not Available")
    email_sent: bool = Field(default=False, description="Always false here; email is a separate explicit call")
    download_available: bool = Field(default=True)


class SendPasswordEmailRequestSchema(BaseModel):
    """
    Request for POST /send-password-email.

    The token identifies the reset. Sending the password itself back to the
    server would put it in a request body and a web server access log.
    """

    username: str = Field(description="The employee whose password was reset")
    password_token: str = Field(description="Token issued by the reset response")


class SendPasswordEmailResponseSchema(BaseModel):
    """Response for POST /send-password-email."""

    status: str = Field(default="success")
    email_sent: bool = Field(default=False)
    recipient: str = Field(default="", description="Manager address the mail went to")
    message: str = Field(default="")


class UserDetailsResponseSchema(BaseModel):
    """Response for a user lookup, including manager information."""

    username: str
    display_name: str = ""
    email: str = ""
    department: str = ""
    job_title: str = ""
    manager_name: str = "Not Available"
    manager_email: str = "Not Available"
# --- END ADDED FOR PASSWORD ENHANCEMENTS ---
