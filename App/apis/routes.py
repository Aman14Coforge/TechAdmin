# """
# API Routes Module
# Author: Roshan
# Purpose: FastAPI route definitions
# """

# from fastapi import APIRouter, HTTPException, Depends
# from loguru import logger
# import uuid
# from typing import Optional

# # TODO: Import actual modules
# # from App.intent.classifier import IntentClassifier
# # from App.intent.metadata_extractor import MetadataExtractor
# # from App.workflow.router import AgentRouter
# # from App.workflow.graph import TechAdminWorkflow

# from .schemas import (
#     UserRequestSchema,
#     APIResponseSchema,
#     APIErrorResponseSchema
# )

# router = APIRouter(prefix="/api/v1", tags=["techadmin"])


# @router.post(
#     "/request",
#     response_model=APIResponseSchema,
#     responses={
#         400: {"model": APIErrorResponseSchema},
#         500: {"model": APIErrorResponseSchema}
#     },
#     summary="Submit a TechAdmin request"
# )
# async def submit_request(request: UserRequestSchema) -> APIResponseSchema:
#     """
#     Submit a user request to the TechAdmin platform.
    
#     The system will:
#     1. Classify the intent
#     2. Extract metadata
#     3. Route to appropriate agent
#     4. Execute the operation
#     5. Return formatted response
    
#     Example:
#     POST /api/v1/request
#     {
#         "user_input": "Reset password for aman.gupta",
#         "request_id": "req_12345"
#     }
    
#     TODO: Implement actual logic
#     """
#     logger.info(f"Received request: {request.user_input}")
    
#     try:
#         # Generate request ID if not provided
#         request_id = request.request_id or f"req_{uuid.uuid4().hex[:8]}"
        
#         # TODO: Implement workflow execution
#         # 1. Instantiate IntentClassifier
#         # 2. Classify intent
#         # 3. Instantiate MetadataExtractor
#         # 4. Extract metadata
#         # 5. Instantiate AgentRouter
#         # 6. Route to agent
#         # 7. Execute workflow
#         # 8. Format response
        
#         response = APIResponseSchema(
#             success=False,
#             request_id=request_id,
#             message="Request processing not yet implemented",
#             error="Workflow not implemented"
#         )
        
#         logger.info(f"Response for {request_id}: {response}")
#         return response
        
#     except Exception as e:
#         logger.error(f"Error processing request: {str(e)}", exc_info=True)
#         raise HTTPException(
#             status_code=500,
#             detail=str(e)
#         )


# @router.get(
#     "/health",
#     response_model=dict,
#     summary="Health check endpoint"
# )
# async def health_check() -> dict:
#     """
#     Health check endpoint to verify service is running.
#     """
#     logger.info("Health check called")
#     return {
#         "status": "healthy",
#         "service": "TechAdmin Agent Platform",
#         "version": "1.0.0"
#     }


# @router.get(
#     "/intents",
#     response_model=dict,
#     summary="Get supported intents"
# )
# async def get_supported_intents() -> dict:
#     """
#     Get list of supported intents.
    
#     TODO: Return actual supported intents from classifier
#     """
#     return {
#         "intents": [
#             "password_reset",
#             "account_unlock",
#             "grant_access",
#             "revoke_access"
#         ]
#     }


"""
API Routes Module
Author: Roshan
Purpose: FastAPI route definitions
"""

from fastapi import APIRouter, HTTPException, Depends
from loguru import logger
import uuid
from typing import Optional

# TODO: Import actual modules
# from App.intent.classifier import IntentClassifier
# from App.intent.metadata_extractor import MetadataExtractor
# from App.workflow.router import AgentRouter
# from App.workflow.graph import TechAdminWorkflow

from .schemas import (
    UserRequestSchema,
    APIResponseSchema,
    APIErrorResponseSchema,
    # --- ADDED FOR PASSWORD ENHANCEMENTS (Amit Bhagat) ---
    SendPasswordEmailRequestSchema,
    SendPasswordEmailResponseSchema,
    # --- END ADDED FOR PASSWORD ENHANCEMENTS ---
)

# --- ADDED FOR PASSWORD ENHANCEMENTS (Amit Bhagat) ---
from App.services.email_service import send_password_email
from App.services.password_vault import password_vault
# --- END ADDED FOR PASSWORD ENHANCEMENTS ---

router = APIRouter(prefix="/api/v1", tags=["techadmin"])


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
        
        # TODO: Implement workflow execution
        # 1. Instantiate IntentClassifier
        # 2. Classify intent
        # 3. Instantiate MetadataExtractor
        # 4. Extract metadata
        # 5. Instantiate AgentRouter
        # 6. Route to agent
        # 7. Execute workflow
        # 8. Format response
        
        response = APIResponseSchema(
            success=False,
            request_id=request_id,
            message="Request processing not yet implemented",
            error="Workflow not implemented"
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


# --- ADDED FOR PASSWORD ENHANCEMENTS (Amit Bhagat) ---
@router.post(
    "/send-password-email",
    response_model=SendPasswordEmailResponseSchema,
    summary="Send a temporary password to the employee's manager",
)
async def send_password_email_endpoint(
    request: SendPasswordEmailRequestSchema,
) -> SendPasswordEmailResponseSchema:
    """
    Email the temporary password to the manager.

    Deliberately a separate endpoint from the password reset. The specification
    forbids automatic email, so nothing in the reset path can reach this code:
    sending requires a second, explicit call made when the operator clicks the
    button.

    The request carries the token rather than the password. Putting the
    password in a request body would place it in the web server's access log,
    which is exactly what the vault indirection exists to avoid.

    Args:
        request: The username and the token from the reset response.

    Returns:
        Whether the mail was sent, and the recipient address.
    """
    logger.info(
        "EMAIL_REQUEST_RECEIVED | target_user={} | token={}",
        request.username,
        request.password_token,
    )

    entry = password_vault.get(request.password_token)

    if entry is None:
        logger.warning(
            "EMAIL_SEND_FAILED | target_user={} | reason=token_expired_or_unknown",
            request.username,
        )
        raise HTTPException(
            status_code=404,
            detail="That password reset is no longer available. Run the reset again.",
        )

    sent, message = send_password_email(
        manager_email=entry.manager_email,
        manager_name=entry.manager_name,
        username=entry.username,
        employee_name=entry.employee_name,
        password=entry.password,
    )

    return SendPasswordEmailResponseSchema(
        status="success" if sent else "error",
        email_sent=sent,
        recipient=entry.manager_email if sent else "",
        message=message,
    )
# --- END ADDED FOR PASSWORD ENHANCEMENTS ---
