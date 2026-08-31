"""
API Request/Response Schemas
Author: Roshan
Purpose: Define Pydantic models for API validation
"""

from pydantic import BaseModel, Field, field_validator
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
    
    @field_validator('user_input')
    @classmethod
    def validate_user_input(cls, v: str) -> str:
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
