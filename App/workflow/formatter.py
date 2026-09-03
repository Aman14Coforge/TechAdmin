"""
Response Formatter Module
Author: Shreesanyog
Purpose: Format technical outputs into user-friendly responses
"""

from typing import Dict, Any
from loguru import logger


class ResponseFormatter:
    """
    Formats technical operation results into user-friendly responses.
    
    TODO: Implement templates for different operation types
    """
    
    @staticmethod
    def format_password_reset_response(
        success: bool,
        username: str,
        result: Dict[str, Any],
        error: str = None
    ) -> str:
        """
        Format password reset operation response.
        
        Args:
            success: Whether operation succeeded
            username: User's username
            result: Operation result details
            error: Error message if failed
            
        Returns:
            User-friendly response message
            
        TODO: Implement with templates
        """
        logger.info(f"Formatting password reset response for {username}")
        
        if success:
            # TODO: Use template system
            message = f"✅ Password reset completed successfully for user '{username}'."
            
            # Demo only - in production deliver this out-of-band, never in the response
            temp_password = (result or {}).get("new_password")
            if temp_password:
                message += f"\nTemporary password: {temp_password}"
            
            return message
        else:
            return (
                f"❌ Password reset failed for user '{username}'.\n"
                f"Error: {error or 'Unknown error'}"
            )
    
    @staticmethod
    def format_account_unlock_response(
        success: bool,
        username: str,
        result: Dict[str, Any] = None,
        error: str = None
    ) -> str:
        """Format account unlock response. TODO: Implement"""
        if success:
            return f"✅ Account unlocked successfully for user '{username}'."
        else:
            return f"❌ Failed to unlock account for user '{username}'.\nError: {error}"
    
    @staticmethod
    def format_error_response(error_message: str, error_details: str = None) -> str:
        """
        Format error response.
        
        Args:
            error_message: Main error message
            error_details: Additional error details
            
        Returns:
            Formatted error message
        """
        logger.error(f"Formatting error response: {error_message}")
        
        if error_details:
            return f"❌ An error occurred: {error_message}\nDetails: {error_details}"
        else:
            return f"❌ An error occurred: {error_message}"