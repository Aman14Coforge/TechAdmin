"""
Get User Details Tool
Author: Aman Mishra
Purpose: Retrieve user details from Azure AD via Microsoft Graph API
"""

from typing import Dict, Any, Optional
from loguru import logger
from App.integration.microsoft_graph import MicrosoftGraphClient


class GetUserDetailsTool:
    """
    Tool to fetch user details from Azure AD.
    Uses Microsoft Graph API to retrieve user information.
    """
    
    def __init__(self, client_id: str = None, client_secret: str = None, tenant_id: str = None):
        """
        Initialize the Get User Details Tool.
        
        Args:
            client_id: Azure AD Application ID
            client_secret: Azure AD Application Secret
            tenant_id: Azure Tenant ID
        """
        self.graph_client = MicrosoftGraphClient(client_id, client_secret, tenant_id)
        logger.info("GetUserDetailsTool initialized")
    
    def get_details(self, user_identifier: str, fields: Optional[list] = None) -> Dict[str, Any]:
        """
        Get user details from Azure AD.
        
        Args:
            user_identifier: User's email or username (e.g., aman.gupta or aman.gupta@coforge.com)
            fields: Optional list of fields to retrieve
            
        Returns:
            Dict containing:
            - success: Whether operation succeeded
            - message: Status message
            - user_data: User details if found
            - error: Error message if failed
        """
        logger.info(f"Getting user details for: {user_identifier}")
        
        try:
            if "@" in user_identifier:
                user_data = self.graph_client.get_user_details(user_identifier, fields)
            else:
                user_data = self.graph_client.find_user_by_username(user_identifier)
            
            if not user_data:
                return {
                    "success": False,
                    "message": f"User '{user_identifier}' not found in Azure AD",
                    "user_data": None,
                    "error": f"User not found: {user_identifier}"
                }
            
            logger.info(f"User details retrieved successfully for: {user_data.get('userPrincipalName')}")
            
            return {
                "success": True,
                "message": f"User details retrieved successfully for {user_data.get('userPrincipalName')}",
                "user_data": user_data,
                "error": None
            }
            
        except Exception as e:
            logger.error(f"Error getting user details: {str(e)}")
            return {
                "success": False,
                "message": "Error retrieving user details",
                "user_data": None,
                "error": str(e)
            }
