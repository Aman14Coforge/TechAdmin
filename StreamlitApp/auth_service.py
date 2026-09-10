"""
TechAdmin Streamlit Authentication Service

Purpose:
    Protect the TechAdmin Streamlit application with Microsoft Entra ID.

Login flow:
    1. User opens TechAdmin.
    2. Streamlit checks whether the user is authenticated.
    3. If not authenticated, only the login page is displayed.
    4. User selects "Sign in with Microsoft".
    5. Microsoft Entra authenticates the organizational user.
    6. Microsoft returns the user to TechAdmin.
    7. Streamlit makes verified identity claims available through st.user.
    8. The existing TechAdmin dashboard is displayed.

Important:
    This authentication is only for employee login.

    It does not replace the GRAPH_* credentials used by the Identity Agent
    for privileged Microsoft Graph operations.
"""

from __future__ import annotations

from typing import Any, Dict

import streamlit as st
from loguru import logger


def get_authenticated_user() -> Dict[str, Any]:
    """
    Return the minimum identity information required by TechAdmin.

    After successful OpenID Connect authentication, Streamlit exposes the
    verified user claims through st.user.

    Tokens, passwords, client secrets, authorization codes, and authentication
    cookies are not returned or logged.

    Returns:
        Dictionary containing basic information about the signed-in employee.
        Returns an empty dictionary when the user is not authenticated.
    """

    if not getattr(st.user, "is_logged_in", False):
        return {}

    # Microsoft Entra normally provides "oid" as the stable user object ID.
    # "sub" is used only as a fallback if oid is unavailable.
    object_id = st.user.get("oid") or st.user.get("sub")

    # Depending on the Entra token configuration, the organizational username
    # may be returned in preferred_username, email, or upn.
    username = (
        st.user.get("preferred_username")
        or st.user.get("email")
        or st.user.get("upn")
    )

    return {
        "object_id": object_id,
        "tenant_id": st.user.get("tid"),
        "name": st.user.get("name") or username or "TechAdmin user",
        "username": username,
    }


def render_login_page() -> None:
    """
    Display the public TechAdmin login page.

    The existing dashboard, example queries, FlowService, Ollama client,
    DemoFlow, and Microsoft Graph client are not initialized on this page.
    """

    # Add some vertical spacing above the login panel.
    st.markdown("<br><br>", unsafe_allow_html=True)

    # Use three columns to center the login content.
    left_column, center_column, right_column = st.columns([1, 2, 1])

    with center_column:
        st.title(" TechAdmin")
        st.subheader("Secure IT Administration Platform")

        st.write(
            "Sign in with your organizational Microsoft account "
            "to access the TechAdmin dashboard."
        )

        st.info(
            "Microsoft Entra ID manages your organizational sign-in, "
            "multifactor authentication, and security policies."
        )

        if st.button(
            "Sign in with Microsoft",
            type="primary",
            use_container_width=True,
        ):
            # The name "microsoft" must match the following section in:
            # .streamlit/secrets.toml
            #
            # [auth.microsoft]
            st.login()

        st.caption(
            "Access is intended only for authorized organizational users."
        )


def require_authentication() -> Dict[str, Any]:
    """
    Protect the Streamlit application.

    This function must be called before:
        - init_state()
        - get_service()
        - FlowService()
        - DemoFlow()
        - Any privileged Microsoft Graph operation

    If the user is not authenticated:
        1. Display the Microsoft login page.
        2. Stop the current Streamlit run.

    If the user is authenticated:
        Return the minimum verified user profile.

    Returns:
        Dictionary containing the authenticated employee identity.
    """

    if not getattr(st.user, "is_logged_in", False):
        render_login_page()

        # This stops app.py immediately.
        # It prevents the existing dashboard and privileged services from
        # loading before successful Microsoft authentication.
        st.stop()

    user = get_authenticated_user()

    # Do not log the full st.user object because it may contain unnecessary
    # authentication claims. Never log tokens, secrets, or authorization codes.
    logger.info(
        "Authenticated TechAdmin session | object_id={}",
        user.get("object_id") or "unavailable",
    )

    return user


def render_authenticated_user(user: Dict[str, Any]) -> None:
    """
    Display the signed-in employee and the sign-out control.

    Call this function from the existing TechAdmin sidebar after successful
    authentication.

    Args:
        user: Identity dictionary returned by require_authentication().
    """

    st.caption("Signed in as")
    st.write(f"**{user.get('name') or 'TechAdmin user'}**")

    if user.get("username"):
        st.caption(user["username"])

    if st.button(
        "Sign out",
        key="techadmin_logout",
        use_container_width=True,
    ):
        # Clear TechAdmin-specific state before removing the login cookie.
        st.session_state.pop("conversation", None)
        st.session_state.pop("queued_query", None)

        # Streamlit removes its authentication cookie and begins a new session.
        st.logout()
