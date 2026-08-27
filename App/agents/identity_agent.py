"""
Identity Agent Module
Author: Shreesanyog
Purpose: Execute identity-related operations (password reset, account unlock, access provisioning)
"""

from typing import Dict, Any, Optional
from loguru import logger


class IdentityAgent:
    """
    Handles all identity-related operations:
    - Password Reset
    - Account Unlock
    - Grant/Revoke Access
    - Get User Details
    """
    
    def __init__(self):
        """Initialize the Identity Agent."""
        self.supported_operations = [
            "password_reset",
            "account_unlock",
            "grant_access",
            "revoke_access",
            "get_user_details"
        ]
        logger.info("IdentityAgent initialized")
    
    def execute(self, operation: str, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute an identity operation.
        
        Args:
            operation: Type of operation (e.g., 'password_reset', 'get_user_details')
            metadata: Metadata required for the operation
                For password_reset:
                - username: User's username
                - user_id: User's ID (optional)
                - email: User's email (optional)
                For get_user_details:
                - username: User's username or email
                
        Returns:
            Dict containing:
            - success: Whether operation succeeded
            - result: Operation result details
            - message: User-friendly message
            - error: Error message if failed
        """
        logger.info(f"Identity Agent executing operation: {operation}")
        logger.debug(f"Metadata: {metadata}")
        
        if operation not in self.supported_operations:
            logger.error(f"Unsupported operation: {operation}")
            return {
                "success": False,
                "result": None,
                "message": f"Operation '{operation}' not supported",
                "error": f"Unsupported operation: {operation}"
            }
        
        # Route to specific operation handler
        if operation == "password_reset":
            return self._handle_password_reset(metadata)
        elif operation == "account_unlock":
            return self._handle_account_unlock(metadata)
        elif operation == "grant_access":
            return self._handle_grant_access(metadata)
        elif operation == "revoke_access":
            return self._handle_revoke_access(metadata)
        elif operation == "get_user_details":
            return self._handle_get_user_details(metadata)
    
    def _handle_get_user_details(self, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle get user details operation.
        """
        logger.info("Processing get user details...")
        
        # Use email if available (LLM already extracted it), fallback to username
        user_identifier = metadata.get("email") or metadata.get("username")
        if not user_identifier:
            return {
                "success": False,
                "result": None,
                "message": "Username or email is required to get user details",
                "error": "Missing user identifier in metadata"
            }
        
        try:
            from App.tools.identity.get_user_details import GetUserDetailsTool
            
            tool = GetUserDetailsTool()
            result = tool.get_details(user_identifier)
            
            return {
                "success": result.get("success", False),
                "result": result.get("user_data"),
                "message": result.get("message"),
                "error": result.get("error")
            }
            
        except Exception as e:
            logger.error(f"Error in get_user_details: {str(e)}")
            return {
                "success": False,
                "result": None,
                "message": "Failed to retrieve user details",
                "error": str(e)
            }
    
    def _handle_password_reset(self, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """
        Handle password reset operation.
        """
        logger.info("Processing password reset...")
        
        username = metadata.get("username")
        if not username:
            return {
                "success": False,
                "result": None,
                "message": "Username is required for password reset",
                "error": "Missing username in metadata"
            }
        
        try:
            from App.tools.identity.reset_password import GraphAPIPasswordResetTool
            
            tool = GraphAPIPasswordResetTool()
            result = tool.reset_password(username)
            
            if result["success"]:
                return {
                    "success": True,
                    "result": result,
                    "message": f"Password reset successful for {username}",
                    "error": None
                }
            else:
                return {
                    "success": False,
                    "result": None,
                    "message": result.get("message", "Password reset failed"),
                    "error": result.get("error")
                }
            
        except Exception as e:
            logger.error(f"Error in password_reset: {str(e)}")
            return {
                "success": False,
                "result": None,
                "message": "Failed to reset password",
                "error": str(e)
            }
    
    def _handle_account_unlock(self, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Handle account unlock operation. TODO: Implement"""
        logger.info("Processing account unlock...")
        return {"success": False, "result": None, "message": "Not implemented", "error": "Account unlock not yet implemented"}
    
    def _handle_grant_access(self, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Handle grant access operation. TODO: Implement"""
        logger.info("Processing grant access...")
        return {"success": False, "result": None, "message": "Not implemented", "error": "Grant access not yet implemented"}
    
    def _handle_revoke_access(self, metadata: Dict[str, Any]) -> Dict[str, Any]:
        """Handle revoke access operation. TODO: Implement"""
        logger.info("Processing revoke access...")
        return {"success": False, "result": None, "message": "Not implemented", "error": "Revoke access not yet implemented"}
