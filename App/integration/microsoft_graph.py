"""
Microsoft Graph API Client Module
Author: Aman Mishra
Purpose: Handle authentication and API calls to Microsoft Graph
"""

from typing import Optional, Dict, Any
from loguru import logger
import os
import requests
import json


class MicrosoftGraphClient:
    """
    Client for Microsoft Graph API.
    Handles authentication and API calls for identity operations.
    Implements OAuth2 client credentials flow.
    """
    
    def __init__(
        self,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        tenant_id: Optional[str] = None
    ):
        """
        Initialize Microsoft Graph API Client.
        
        Args:
            client_id: Azure AD Application ID (from .env if not provided)
            client_secret: Azure AD Application Secret (from .env if not provided)
            tenant_id: Azure Tenant ID (from .env if not provided)
        """
        self.client_id = client_id or os.getenv("GRAPH_CLIENT_ID")
        self.client_secret = client_secret or os.getenv("GRAPH_CLIENT_SECRET")
        self.tenant_id = tenant_id or os.getenv("GRAPH_TENANT_ID")
        self.graph_api_url = "https://graph.microsoft.com/v1.0"
        self.token_url = f"https://login.microsoftonline.com/{self.tenant_id}/oauth2/v2.0/token"
        self.access_token = None
        
        logger.info("MicrosoftGraphClient initialized")
    
    def authenticate(self) -> bool:
        """
        Authenticate with Microsoft Graph API using OAuth2 client credentials flow.
        
        Returns:
            True if authentication successful, False otherwise
        """
        logger.info("Authenticating with Microsoft Graph API...")
        
        try:
            if not all([self.client_id, self.client_secret, self.tenant_id]):
                logger.error("Missing required credentials: client_id, client_secret, or tenant_id")
                return False
            
            # Prepare token request
            data = {
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "scope": "https://graph.microsoft.com/.default",
                "grant_type": "client_credentials"
            }
            
            logger.debug(f"Requesting token from: {self.token_url}")
            
            # Get access token
            response = requests.post(self.token_url, data=data, timeout=10)
            response.raise_for_status()
            
            token_data = response.json()
            self.access_token = token_data.get("access_token")
            
            if not self.access_token:
                logger.error("No access token in response")
                return False
            
            logger.info("Authentication successful - Access token obtained")
            return True
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Authentication failed: {str(e)}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error during authentication: {str(e)}")
            return False
    
    def get_user_details(self, user_identifier: str, select_fields: Optional[list] = None) -> Optional[Dict[str, Any]]:
        """
        Get user details from Azure AD by email or user ID.
        
        Args:
            user_identifier: User's email (e.g., aman.gupta@company.com) or user ID
            select_fields: List of fields to retrieve (default: id, displayName, userPrincipalName, accountEnabled)
            
        Returns:
            User object with requested properties, or None if not found
        """
        logger.info(f"Fetching user details for: {user_identifier}")
        
        try:
            if not self.access_token:
                logger.error("Not authenticated. Call authenticate() first.")
                return None
            
            # Default fields to retrieve
            if select_fields is None:
                select_fields = ["id", "displayName", "userPrincipalName", "accountEnabled", "onPremisesSyncEnabled", "userType", "mail"]
            
            select_param = ",".join(select_fields)
            
            # Build URL - use user_identifier as-is (email or ID)
            url = f"{self.graph_api_url}/users/{user_identifier}?$select={select_param}"
            
            # Prepare headers
            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json"
            }
            
            logger.debug(f"Calling Graph API: {url}")
            
            # Make request
            response = requests.get(url, headers=headers, timeout=10)
            
            if response.status_code == 404:
                logger.warning(f"User not found: {user_identifier}")
                return None
            
            response.raise_for_status()
            
            user_data = response.json()
            logger.info(f"User details retrieved successfully: {user_data.get('userPrincipalName')}")
            
            return user_data
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching user details: {str(e)}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error: {str(e)}")
            return None
    
    def find_user_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        """
        Find user in Azure AD by username.
        
        Args:
            username: User's username (e.g., aman.gupta)
            
        Returns:
            User object with id and properties, or None if not found
        """
        logger.info(f"Finding user by username: {username}")
        
        try:
            if not self.access_token:
                logger.error("Not authenticated. Call authenticate() first.")
                return None
            
            # Try to search by userPrincipalName with common domain patterns
            common_domains = ["coforge.com", "company.com", "outlook.com"]
            
            for domain in common_domains:
                user_email = f"{username}@{domain}"
                logger.debug(f"Trying: {user_email}")
                
                user_data = self.get_user_details(user_email)
                if user_data:
                    return user_data
            
            logger.warning(f"User not found with username: {username}")
            return None
            
        except Exception as e:
            logger.error(f"Error finding user: {str(e)}")
            return None
    
    def change_password(self, user_id: str, new_password: str) -> bool:
        """
        Change password for a user.
        
        Args:
            user_id: Azure AD user ID or userPrincipalName
            new_password: New password to set
            
        Returns:
            True if successful, False otherwise
        """
        logger.info(f"Changing password for user: {user_id}")
        
        try:
            if not self.access_token:
                logger.error("Not authenticated. Call authenticate() first.")
                return False
            
            url = f"{self.graph_api_url}/users/{user_id}/changePassword"
            
            headers = {
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json"
            }
            
            payload = {
                "currentPassword": "",  # Empty for admin operation
                "newPassword": new_password
            }
            
            logger.debug(f"Calling Graph API: {url}")
            
            response = requests.post(url, headers=headers, json=payload, timeout=10)
            response.raise_for_status()
            
            logger.info(f"Password changed successfully for user: {user_id}")
            return True
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Error changing password: {str(e)}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error: {str(e)}")
            return False
    
    def reset_password(self, user_id: str) -> Optional[str]:
        """
        Reset password for a user (admin operation).
        Generates a temporary password.
        
        Args:
            user_id: Azure AD user ID
            
        Returns:
            Temporary password if successful, None otherwise
        """
        logger.info(f"Resetting password for user: {user_id}")
        
        try:
            if not self.access_token:
                logger.error("Not authenticated. Call authenticate() first.")
                return None
            
            # For now, use the changePassword method with a temporary password
            import secrets
            import string
            
            # Generate a secure temporary password
            alphabet = string.ascii_letters + string.digits + "!@#$%^&*"
            temp_password = ''.join(secrets.choice(alphabet) for i in range(12))
            
            if self.change_password(user_id, temp_password):
                logger.info(f"Password reset successfully for user: {user_id}")
                return temp_password
            else:
                return None
            
        except Exception as e:
            logger.error(f"Error resetting password: {str(e)}")
            return None
