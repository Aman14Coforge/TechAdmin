"""
Password Reset Tool Module
Author: Aman Mishra
Purpose: Interface for password reset operations via Microsoft Graph API
"""

from typing import Dict, Any, Optional
from loguru import logger
from App.integration.microsoft_graph import MicrosoftGraphClient


class GraphAPIPasswordResetTool:
    """
    Password Reset Tool using Microsoft Graph API.
    Handles password reset via Azure AD.
    """
    
    def __init__(self, client_id: str = None, client_secret: str = None, tenant_id: str = None):
        """
        Initialize the Password Reset Tool.
        
        Args:
            client_id: Azure AD Application ID
            client_secret: Azure AD Application Secret
            tenant_id: Azure Tenant ID
        """
        self.graph_client = MicrosoftGraphClient(client_id, client_secret, tenant_id)
        logger.info("GraphAPIPasswordResetTool initialized")
    
    def reset_password(self, username: str) -> Dict[str, Any]:
        """
        Reset password for the given username using Microsoft Graph API.
        
        Args:
            username: User's username (e.g., aman.gupta or aman.gupta@coforge.com)
            
        Returns:
            Dict containing:
            - success: Whether password reset was successful
            - message: Result message
            - user_id: User's ID (if found)
            - new_password: Temporary password (if applicable)
            - error: Error message if failed
        """
        logger.info(f"Attempting to reset password for user: {username}")
        
        try:
            # Find user (handles both bare usernames and full UPNs)
            logger.info(f"Finding user: {username}")
            user_data = self.graph_client.find_user_by_username(username)
            
            if not user_data:
                logger.error(f"User not found: {username}")
                return {
                    "success": False,
                    "message": f"User '{username}' not found in Azure AD",
                    "user_id": None,
                    "new_password": None,
                    "error": f"User not found: {username}"
                }
            
            user_id = user_data.get("id")
            user_principal = user_data.get("userPrincipalName")
            
            logger.info(f"Found user: {user_principal} (ID: {user_id})")
            
            # Reset password
            logger.info(f"Resetting password for user ID: {user_id}")
            temp_password = self.graph_client.reset_password(user_id)
            
            if not temp_password:
                logger.error("Password reset failed")
                return {
                    "success": False,
                    "message": "Failed to reset password",
                    "user_id": user_id,
                    "new_password": None,
                    "error": "Password reset API call failed"
                }
            
            logger.info(f"Password reset successful for user: {user_principal}")
            
            return {
                "success": True,
                "message": f"Password reset successful for {user_principal}. Temporary password has been generated.",
                "user_id": user_id,
                "user_principal": user_principal,
                "new_password": temp_password,  # In production, this should be sent via email only
                "error": None
            }
            
        except Exception as e:
            logger.error(f"Error resetting password: {str(e)}", exc_info=True)
            return {
                "success": False,
                "message": "Error resetting password",
                "user_id": None,
                "new_password": None,
                "error": str(e)
            }
    
    def validate_username(self, username: str) -> tuple:
        """
        Validate that the username exists in AD.
        
        Args:
            username: Username to validate
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        if not username or len(username) < 3:
            return False, "Invalid username format"
        
        try:
            # Authenticate if needed
            if not self.graph_client.access_token:
                if not self.graph_client.authenticate():
                    return False, "Authentication failed"
            
            # Try to find user
            if "@" not in username:
                user_data = self.graph_client.find_user_by_username(username)
            else:
                user_data = self.graph_client.get_user_details(username)
            
            if user_data:
                return True, "Username is valid"
            else:
                return False, "User not found in Azure AD"
                
        except Exception as e:
            logger.error(f"Error validating username: {str(e)}")
            return False, f"Validation error: {str(e)}"
