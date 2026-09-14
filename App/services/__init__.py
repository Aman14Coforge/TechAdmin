"""
Services Package
Author: Amit Bhagat
Purpose: Side-effecting services used by the password reset enhancements.

Modules:
    password_vault   Holds an original password server-side so it never travels
                     in an API response
    password_file    Builds the downloadable TXT file
    email_service    Sends the password to the manager on explicit request
"""
