"""
Microsoft Graph API Client Module
Author: Aman Mishra
Purpose: Handle authentication and API calls to Microsoft Graph
"""

from typing import Optional, Dict, Any
from loguru import logger
import os
import time
import requests
import json


class MicrosoftGraphClient:
    """
    Client for Microsoft Graph API.
    Handles authentication and API calls for identity operations.
    Implements OAuth2 client credentials flow.
    """
    
    PASSWORD_METHOD_ID = "28c10230-6103-485e-b985-444c60001490"
    
    def __init__(
        self,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        tenant_id: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        auth_mode: Optional[str] = None
    ):
        """
        Initialize Microsoft Graph API Client.
        
        Args:
            client_id: Azure AD Application ID (from .env if not provided)
            client_secret: Azure AD Application Secret (from .env if not provided)
            tenant_id: Azure Tenant ID (from .env if not provided)
            username: Service account UPN for delegated auth (from .env if not provided)
            password: Service account password for delegated auth (from .env if not provided)
            auth_mode: "delegated" (username/password) or "application" (client credentials)
        """
        self.client_id = client_id or os.getenv("GRAPH_CLIENT_ID")
        self.client_secret = client_secret or os.getenv("GRAPH_CLIENT_SECRET")
        self.tenant_id = tenant_id or os.getenv("GRAPH_TENANT_ID")
        self.username = username or os.getenv("GRAPH_USERNAME")
        self.password = password or os.getenv("GRAPH_PASSWORD")
        self.auth_mode = (auth_mode or os.getenv("GRAPH_AUTH_MODE", "delegated")).lower()
        self.scope = os.getenv(
            "GRAPH_DELEGATED_SCOPE",
            "https://graph.microsoft.com/User.Read.All https://graph.microsoft.com/User.ReadWrite.All offline_access"
        )
        self.graph_api_url = "https://graph.microsoft.com/v1.0"
        self.token_url = f"https://login.microsoftonline.com/{self.tenant_id}/oauth2/v2.0/token"
        self.access_token = None
        self._token_expires_at = 0.0
        
        logger.info(f"MicrosoftGraphClient initialized (auth_mode={self.auth_mode})")
    
    def _ensure_token(self) -> bool:
        """Return True if a valid cached token exists, re-authenticating if needed."""
        if self.access_token and time.time() < self._token_expires_at:
            return True
        return self.authenticate()
    
    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }
    
    @staticmethod
    def _log_graph_error(response: requests.Response, context: str) -> None:
        try:
            graph_error = response.json().get("error", {})
        except ValueError:
            graph_error = {}
        logger.error(
            f"{context} failed ({response.status_code}): "
            f"{graph_error.get('code')} - {graph_error.get('message')}"
        )
    
    def authenticate(self) -> bool:
        """
        Authenticate with Microsoft Graph API.
        Uses delegated (username/password) flow by default, or client credentials
        when GRAPH_AUTH_MODE=application.
        
        Returns:
            True if authentication successful, False otherwise
        """
        logger.info(f"Authenticating with Microsoft Graph API (mode={self.auth_mode})...")
        
        try:
            if not all([self.client_id, self.tenant_id]):
                logger.error("Missing required credentials: client_id or tenant_id")
                return False
            
            if self.auth_mode == "delegated":
                if not all([self.username, self.password]):
                    logger.error("Missing GRAPH_USERNAME or GRAPH_PASSWORD for delegated auth")
                    return False
                
                data = {
                    "client_id": self.client_id,
                    "scope": self.scope,
                    "username": self.username,
                    "password": self.password,
                    "grant_type": "password"
                }
                # Confidential clients must also send the secret
                if self.client_secret:
                    data["client_secret"] = self.client_secret
            else:
                if not self.client_secret:
                    logger.error("Missing GRAPH_CLIENT_SECRET for application auth")
                    return False
                
                data = {
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "scope": "https://graph.microsoft.com/.default",
                    "grant_type": "client_credentials"
                }
            
            logger.debug(f"Requesting token from: {self.token_url}")
            
            response = requests.post(self.token_url, data=data, timeout=10)
            
            if response.status_code != 200:
                error_data = response.json() if response.content else {}
                logger.error(
                    f"Token request failed ({response.status_code}): "
                    f"{error_data.get('error')} - {error_data.get('error_description', '')[:300]}"
                )
                return False
            
            token_data = response.json()
            self.access_token = token_data.get("access_token")
            
            if not self.access_token:
                logger.error("No access token in response")
                return False
            
            # Refresh 60s early to avoid using a token that expires mid-request
            self._token_expires_at = time.time() + int(token_data.get("expires_in", 3600)) - 60
            
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
            if not self._ensure_token():
                logger.error("Unable to obtain access token")
                return None
            
            # Default fields to retrieve
            if select_fields is None:
                select_fields = ["id", "displayName", "userPrincipalName", "accountEnabled", "onPremisesSyncEnabled", "userType", "mail"]
            
            select_param = ",".join(select_fields)
            
            # Build URL - use user_identifier as-is (email or ID)
            url = f"{self.graph_api_url}/users/{user_identifier}?$select={select_param}"
            
            logger.debug(f"Calling Graph API: {url}")
            
            response = requests.get(url, headers=self._headers(), timeout=10)
            
            if response.status_code == 404:
                logger.warning(f"User not found: {user_identifier}")
                return None
            
            if response.status_code != 200:
                self._log_graph_error(response, "Get user details")
                return None
            
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
        Find user in Azure AD by username, email, or display name.
        
        Args:
            username: User's username (e.g., aman.gupta), UPN, or display name
            
        Returns:
            User object with id and properties, or None if not found/ambiguous
        """
        logger.info(f"Finding user by username: {username}")
        
        try:
            if not self._ensure_token():
                logger.error("Unable to obtain access token")
                return None
            
            # A full UPN can be looked up directly
            if "@" in username:
                return self.get_user_details(username)
            
            select_param = "id,displayName,userPrincipalName,accountEnabled,onPremisesSyncEnabled,userType,mail"
            escaped = username.replace("'", "''")
            filter_param = (
                f"startswith(userPrincipalName,'{escaped}@') "
                f"or mailNickname eq '{escaped}' "
                f"or startswith(displayName,'{escaped}')"
            )
            
            url = f"{self.graph_api_url}/users"
            params = {"$select": select_param, "$filter": filter_param, "$top": "10"}
            
            logger.debug(f"Searching users with filter: {filter_param}")
            
            response = requests.get(url, headers=self._headers(), params=params, timeout=10)
            
            if response.status_code != 200:
                self._log_graph_error(response, "User search")
                return None
            
            matches = response.json().get("value", [])
            
            if not matches:
                logger.warning(f"User not found with username: {username}")
                return None
            
            if len(matches) > 1:
                upns = [m.get("userPrincipalName") for m in matches]
                logger.warning(f"Ambiguous username '{username}' matched {len(matches)} users: {upns}")
                return None
            
            logger.info(f"User found: {matches[0].get('userPrincipalName')}")
            return matches[0]
            
        except Exception as e:
            logger.error(f"Error finding user: {str(e)}")
            return None
    
    def change_password(self, user_id: str, new_password: str) -> bool:
        """
        Set a user's password as an administrator via the authentication methods API.
        POST /users/{id}/authentication/methods/{passwordMethodId}/resetPassword
        
        Args:
            user_id: Azure AD user ID or userPrincipalName
            new_password: New password to set
            
        Returns:
            True if successful, False otherwise
        """
        logger.info(f"Setting password for user: {user_id}")
        
        try:
            if not self._ensure_token():
                logger.error("Unable to obtain access token")
                return False
            
            # Well-known ID of the password authentication method; identical for every user
            url = (
                f"{self.graph_api_url}/users/{user_id}"
                f"/authentication/methods/{self.PASSWORD_METHOD_ID}/resetPassword"
            )
            
            payload = {"newPassword": new_password}
            
            logger.debug(f"Calling Graph API: POST {url}")
            
            response = requests.post(url, headers=self._headers(), json=payload, timeout=15)
            
            if response.status_code not in (200, 202):
                self._log_graph_error(response, "Password reset")
                return False
            
            # 202 Accepted: the reset is async, poll the Location header for the outcome
            status_url = response.headers.get("Location")
            if status_url and not self._await_reset(status_url):
                return False
            
            logger.info(f"Password changed successfully for user: {user_id}")
            return True
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Error changing password: {str(e)}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error: {str(e)}")
            return False
    
    def _await_reset(self, status_url: str, attempts: int = 6, interval: float = 3.0) -> bool:
        """
        Poll a password-reset operation for its outcome.
        Only an explicit 'failed' status is treated as failure; if the operation
        cannot be read (Graph often denies the operations endpoint) the 202 from
        the reset call is taken as authoritative.
        """
        for attempt in range(attempts):
            time.sleep(interval)
            
            response = requests.get(status_url, headers=self._headers(), timeout=10)
            
            if response.status_code not in (200, 202):
                logger.warning(
                    f"Could not read password reset status ({response.status_code}); "
                    "reset was accepted by Graph, treating as submitted"
                )
                return True
            
            status = (response.json().get("status") or "").lower()
            logger.debug(f"Password reset status (attempt {attempt + 1}): {status}")
            
            if status == "succeeded":
                return True
            if status == "failed":
                logger.error("Password reset operation reported status 'failed'")
                return False
        
        logger.warning("Password reset still in progress after polling; treating as submitted")
        return True
    
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
            if not self._ensure_token():
                logger.error("Unable to obtain access token")
                return None
            
            temp_password = self.generate_temp_password()
            
            if self.change_password(user_id, temp_password):
                logger.info(f"Password reset successfully for user: {user_id}")
                return temp_password
            
            return None
            
        except Exception as e:
            logger.error(f"Error resetting password: {str(e)}")
            return None
    
    @staticmethod
    def generate_temp_password() -> str:
        """
        Generate a temporary password shaped like 'Kanoteru@4820513$'.
        Uses pronounceable syllables and only '@'/'$' because on-prem synced
        accounts reject some symbols that Azure AD alone would accept.
        """
        import secrets
        
        consonants = "bdfghjklmnprstvwz"
        vowels = "aeiou"
        rng = secrets.SystemRandom()
        
        def syllables(count: int) -> str:
            return "".join(rng.choice(consonants) + rng.choice(vowels) for _ in range(count))
        
        first = syllables(2).capitalize()
        second = syllables(2)
        digits = "".join(rng.choice("0123456789") for _ in range(7))
        
        return f"{first}{second}@{digits}$"