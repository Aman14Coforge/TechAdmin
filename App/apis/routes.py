"""
API Routes Module
Author: Roshan
Purpose: FastAPI route definitions
"""

from fastapi import APIRouter, HTTPException, Depends
from loguru import logger
import uuid
from typing import Optional

from App.workflow.graph import TechAdminWorkflow
from .schemas import (
    UserRequestSchema,
    APIResponseSchema,
    APIErrorResponseSchema
)

router = APIRouter(prefix="/api/v1", tags=["techadmin"])

# Initialize workflow engine
workflow = TechAdminWorkflow()


@router.post(
    "/request",
    response_model=APIResponseSchema,
    responses={
        400: {"model": APIErrorResponseSchema},
        500: {"model": APIErrorResponseSchema}
    },
    summary="Submit a TechAdmin request"
)
async def submit_request(request: UserRequestSchema) -> APIResponseSchema:
    """
    Submit a user request to the TechAdmin platform.
    
    The system will:
    1. Classify the intent
    2. Extract metadata
    3. Route to appropriate agent
    4. Execute the operation
    5. Return formatted response
    
    Example:
    POST /api/v1/request
    {
        "user_input": "Reset password for aman.gupta",
        "request_id": "req_12345"
    }
    
    TODO: Implement actual logic
    """
    logger.info(f"Received request: {request.user_input}")
    
    try:
        # Generate request ID if not provided
        request_id = request.request_id or f"req_{uuid.uuid4().hex[:8]}"
        
        # Execute workflow engine
        result = workflow.execute(
            user_input=request.user_input,
            request_id=request_id
        )
        
        # Package into APIResponseSchema envelope
        response = APIResponseSchema(
            success=result.get("success", False),
            request_id=request_id,
            intent=result.get("intent"),
            message=result.get("response", "Request processed."),
            metadata=result.get("metadata"),
            result=result.get("execution_details"),
            error=result.get("error")
        )
        logger.info(f"Response for {request_id}: {response}")
        return response
        
    except Exception as e:
        logger.error(f"Error processing request: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )


@router.get(
    "/health",
    response_model=dict,
    summary="Health check endpoint"
)
async def health_check() -> dict:
    """
    Health check endpoint to verify service is running.
    """
    logger.info("Health check called")
    return {
        "status": "healthy",
        "service": "TechAdmin Agent Platform",
        "version": "1.0.0"
    }


@router.get(
    "/intents",
    response_model=dict,
    summary="Get supported intents"
)
async def get_supported_intents() -> dict:
    """
    Get list of supported intents.
    
    TODO: Return actual supported intents from classifier
    """
    return {
        "intents": [
            "password_reset",
            "account_unlock",
            "grant_access",
            "revoke_access"
        ]
    }
