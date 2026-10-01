"""Microsoft Graph API client for TechAdmin.

Provides:
- OAuth 2.0 client-credential and optional delegated password authentication
- User lookup by UPN, object ID, or unqualified username
- Complete normalized user details for the TechAdmin dashboard
- Manager lookup
- Direct and transitive group membership lookup
- Password reset support

For production service-to-service execution, set GRAPH_AUTH_MODE=application.
"""
from __future__ import annotations

import os
import secrets
import time
from typing import Any, Dict, Optional
from urllib.parse import quote

import requests
from loguru import logger


class MicrosoftGraphClient:
    """Microsoft Graph client used by TechAdmin identity tools."""

    PASSWORD_METHOD_ID = "28c10230-6103-485e-b985-444c60001490"
    GRAPH_API_URL = "https://graph.microsoft.com/v1.0"

    USER_FIELDS = (
        "id",
        "accountEnabled",
        "displayName",
        "givenName",
        "surname",
        "userPrincipalName",
        "mail",
        "mobilePhone",
        "businessPhones",
        "department",
        "jobTitle",
        "officeLocation",
        "employeeId",
        "employeeType",
        "companyName",
        "createdDateTime",
        "userType",
        "onPremisesSamAccountName",
        "onPremisesDistinguishedName",
        "onPremisesDomainName",
        "onPremisesSyncEnabled",
        "onPremisesLastSyncDateTime",
        "passwordPolicies",
        "lastPasswordChangeDateTime",
    )

    MANAGER_FIELDS = (
        "id",
        "accountEnabled",
        "displayName",
        "userPrincipalName",
        "mail",
        "jobTitle",
        "department",
        "onPremisesSamAccountName",
    )

    GROUP_FIELDS = (
        "id",
        "displayName",
        "description",
        "mail",
        "mailEnabled",
        "securityEnabled",
        "groupTypes",
        "onPremisesSamAccountName",
        "onPremisesSecurityIdentifier",
        "onPremisesSyncEnabled",
        "visibility",
    )

    def __init__(
        self,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        tenant_id: Optional[str] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        auth_mode: Optional[str] = None,
        timeout_seconds: Optional[int] = None,
        verify_ssl: Optional[bool] = None,
    ) -> None:
        self.client_id = client_id or os.getenv("GRAPH_CLIENT_ID")
        self.client_secret = client_secret or os.getenv("GRAPH_CLIENT_SECRET")
        self.tenant_id = tenant_id or os.getenv("GRAPH_TENANT_ID")
        self.username = username or os.getenv("GRAPH_USERNAME")
        self.password = password or os.getenv("GRAPH_PASSWORD")
        self.auth_mode = (
            auth_mode or os.getenv("GRAPH_AUTH_MODE", "application")
        ).strip().casefold()
        self.delegated_scope = os.getenv(
            "GRAPH_DELEGATED_SCOPE",
            "User.Read.All User.ReadWrite.All GroupMember.Read.All offline_access",
        )
        self.graph_api_url = self.GRAPH_API_URL
        self.token_url = (
            f"https://login.microsoftonline.com/{self.tenant_id}"
            "/oauth2/v2.0/token"
        )
        self.timeout_seconds = (
            timeout_seconds
            if timeout_seconds is not None
            else int(os.getenv("GRAPH_TIMEOUT_SECONDS", "60"))
        )
        self.verify_ssl = (
            verify_ssl
            if verify_ssl is not None
            else os.getenv("GRAPH_VERIFY_SSL", "true").strip().casefold()
            in {"1", "true", "yes", "on"}
        )
        self.access_token: Optional[str] = None
        self._token_expires_at = 0.0

        logger.info(
            "MicrosoftGraphClient initialized | auth_mode={}",
            self.auth_mode,
        )

    def _ensure_token(self) -> bool:
        if self.access_token and time.time() < self._token_expires_at:
            return True
        return self.authenticate()

    def _headers(self) -> Dict[str, str]:
        if not self.access_token:
            raise RuntimeError("Microsoft Graph access token is unavailable.")
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    @staticmethod
    def _graph_error_message(response: requests.Response) -> str:
        try:
            payload = response.json()
        except ValueError:
            return response.text[:1000] or "No response body"

        if isinstance(payload, dict):
            error = payload.get("error")
            if isinstance(error, dict):
                return str(
                    error.get("message")
                    or error.get("code")
                    or "Microsoft Graph error"
                )
        return str(payload)[:1000]

    @classmethod
    def _log_graph_error(
        cls,
        response: requests.Response,
        context: str,
    ) -> None:
        logger.error(
            "{} failed | status={} | message={}",
            context,
            response.status_code,
            cls._graph_error_message(response),
        )

    def authenticate(self) -> bool:
        """Authenticate and cache a Microsoft Graph access token."""
        try:
            if not self.client_id or not self.tenant_id:
                logger.error("Missing GRAPH_CLIENT_ID or GRAPH_TENANT_ID")
                return False

            if self.auth_mode == "delegated":
                if not self.username or not self.password:
                    logger.error(
                        "Missing GRAPH_USERNAME or GRAPH_PASSWORD for delegated auth"
                    )
                    return False
                data: Dict[str, str] = {
                    "client_id": self.client_id,
                    "scope": self.delegated_scope,
                    "username": self.username,
                    "password": self.password,
                    "grant_type": "password",
                }
                if self.client_secret:
                    data["client_secret"] = self.client_secret
            elif self.auth_mode == "application":
                if not self.client_secret:
                    logger.error("Missing GRAPH_CLIENT_SECRET for application auth")
                    return False
                data = {
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "scope": "https://graph.microsoft.com/.default",
                    "grant_type": "client_credentials",
                }
            else:
                logger.error("Unsupported GRAPH_AUTH_MODE: {}", self.auth_mode)
                return False

            response = requests.post(
                self.token_url,
                data=data,
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
                timeout=self.timeout_seconds,
                verify=self.verify_ssl,
            )

            if response.status_code != 200:
                self._log_graph_error(response, "Graph authentication")
                return False

            token_data = response.json()
            token = token_data.get("access_token")
            if not isinstance(token, str) or not token:
                logger.error("Graph authentication returned no access token")
                return False

            try:
                expires_in = int(token_data.get("expires_in", 3600))
            except (TypeError, ValueError):
                expires_in = 3600

            self.access_token = token
            self._token_expires_at = time.time() + max(60, expires_in - 120)
            logger.info("Microsoft Graph authentication successful")
            return True

        except requests.RequestException as exc:
            logger.error(
                "Microsoft Graph authentication request failed | type={}",
                type(exc).__name__,
            )
            return False
        except Exception as exc:
            logger.exception(
                "Unexpected Microsoft Graph authentication failure | type={}",
                type(exc).__name__,
            )
            return False

    def _get_json(
        self,
        url: str,
        *,
        params: Optional[Dict[str, str]] = None,
        allow_not_found: bool = False,
    ) -> Optional[Dict[str, Any]]:
        if not self._ensure_token():
            return None

        try:
            response = requests.get(
                url,
                headers=self._headers(),
                params=params,
                timeout=self.timeout_seconds,
                verify=self.verify_ssl,
            )
        except requests.RequestException as exc:
            logger.error(
                "Microsoft Graph GET failed | type={} | url={}",
                type(exc).__name__,
                url,
            )
            return None

        if allow_not_found and response.status_code == 404:
            return None

        if response.status_code != 200:
            self._log_graph_error(response, f"Graph GET {url}")
            return None

        try:
            payload = response.json()
        except ValueError:
            logger.error("Microsoft Graph returned invalid JSON | url={}", url)
            return None

        return payload if isinstance(payload, dict) else None

    def _get_collection(
        self,
        url: str,
        *,
        params: Optional[Dict[str, str]] = None,
    ) -> Optional[list[Dict[str, Any]]]:
        rows: list[Dict[str, Any]] = []
        next_url: Optional[str] = url
        next_params = params

        while next_url:
            payload = self._get_json(next_url, params=next_params)
            next_params = None
            if payload is None:
                return None

            values = payload.get("value")
            if isinstance(values, list):
                rows.extend(item for item in values if isinstance(item, dict))

            next_link = payload.get("@odata.nextLink")
            next_url = (
                next_link
                if isinstance(next_link, str) and next_link
                else None
            )

        return rows

    @staticmethod
    def _encoded_identifier(user_identifier: str) -> str:
        value = str(user_identifier or "").strip()
        if not value:
            raise ValueError("User identifier cannot be empty.")
        return quote(value, safe="")

    def get_user_details(
        self,
        user_identifier: str,
        select_fields: Optional[list[str]] = None,
    ) -> Optional[Dict[str, Any]]:
        """Return the raw Graph user object with explicitly selected fields."""
        fields = select_fields or list(self.USER_FIELDS)
        encoded = self._encoded_identifier(user_identifier)
        return self._get_json(
            f"{self.graph_api_url}/users/{encoded}",
            params={"$select": ",".join(fields)},
            allow_not_found=True,
        )

    def find_user_by_username(
        self,
        username: str,
    ) -> Optional[Dict[str, Any]]:
        """Resolve a unique Graph user by UPN or unqualified username."""
        value = str(username or "").strip()
        if not value:
            return None
        if "@" in value:
            return self.get_user_details(value)

        escaped = value.replace("'", "''")
        matches = self._get_collection(
            f"{self.graph_api_url}/users",
            params={
                "$select": ",".join(self.USER_FIELDS),
                "$filter": (
                    f"startswith(userPrincipalName,'{escaped}@') "
                    f"or mailNickname eq '{escaped}' "
                    f"or startswith(displayName,'{escaped}')"
                ),
                "$top": "10",
            },
        )
        if not matches:
            return None
        if len(matches) > 1:
            logger.warning(
                "Ambiguous Graph username | username={} | matches={}",
                value,
                [item.get("userPrincipalName") for item in matches],
            )
            return None
        return matches[0]

    def get_manager(
        self,
        user_identifier: str,
    ) -> Dict[str, Any]:
        """Return manager information without failing the parent lookup."""
        unavailable = {
            "manager_id": None,
            "manager_name": None,
            "manager_email": None,
            "manager_user_principal_name": None,
            "manager_sam_account_name": None,
            "manager_job_title": None,
            "manager_department": None,
            "manager_enabled": None,
        }
        encoded = self._encoded_identifier(user_identifier)
        manager = self._get_json(
            f"{self.graph_api_url}/users/{encoded}/manager",
            params={"$select": ",".join(self.MANAGER_FIELDS)},
            allow_not_found=True,
        )
        if not isinstance(manager, dict):
            return unavailable

        return {
            "manager_id": manager.get("id"),
            "manager_name": (
                manager.get("displayName")
                or manager.get("userPrincipalName")
            ),
            "manager_email": (
                manager.get("mail")
                or manager.get("userPrincipalName")
            ),
            "manager_user_principal_name": manager.get("userPrincipalName"),
            "manager_sam_account_name": manager.get(
                "onPremisesSamAccountName"
            ),
            "manager_job_title": manager.get("jobTitle"),
            "manager_department": manager.get("department"),
            "manager_enabled": manager.get("accountEnabled"),
        }

    def get_direct_groups(
        self,
        user_identifier: str,
    ) -> Optional[list[Dict[str, Any]]]:
        encoded = self._encoded_identifier(user_identifier)
        return self._get_collection(
            f"{self.graph_api_url}/users/{encoded}/memberOf/"
            "microsoft.graph.group",
            params={
                "$select": ",".join(self.GROUP_FIELDS),
                "$top": "999",
            },
        )

    def get_transitive_groups(
        self,
        user_identifier: str,
    ) -> Optional[list[Dict[str, Any]]]:
        encoded = self._encoded_identifier(user_identifier)
        return self._get_collection(
            f"{self.graph_api_url}/users/{encoded}/transitiveMemberOf/"
            "microsoft.graph.group",
            params={
                "$select": ",".join(self.GROUP_FIELDS),
                "$top": "999",
            },
        )

    @staticmethod
    def _normalize_group(
        group: Dict[str, Any],
        membership_type: str,
    ) -> Dict[str, Any]:
        if group.get("securityEnabled") is True:
            category = "Security"
        elif group.get("mailEnabled") is True:
            category = "Distribution"
        else:
            category = None

        group_types = group.get("groupTypes")
        if not isinstance(group_types, list):
            group_types = []

        return {
            "Name": group.get("displayName"),
            "SamAccountName": group.get("onPremisesSamAccountName"),
            "DistinguishedName": None,
            "GroupCategory": category,
            "GroupScope": None,
            "Description": group.get("description"),
            "MembershipType": membership_type,
            "NestingLevel": 0 if membership_type == "Direct" else None,
            "InheritedFrom": None,
            "ResolutionError": None,
            "GraphId": group.get("id"),
            "Mail": group.get("mail"),
            "MailEnabled": group.get("mailEnabled"),
            "SecurityEnabled": group.get("securityEnabled"),
            "GroupTypes": group_types,
            "Visibility": group.get("visibility"),
            "OnPremisesSyncEnabled": group.get("onPremisesSyncEnabled"),
        }

    def get_complete_user_details(
        self,
        user_identifier: str,
    ) -> Optional[Dict[str, Any]]:
        """Return the normalized user model consumed by the TechAdmin UI."""
        user = self.get_user_details(user_identifier)
        if not isinstance(user, dict):
            return None

        user_id = user.get("id")
        if not isinstance(user_id, str) or not user_id:
            logger.error("Graph user response contains no object ID")
            return None

        manager = self.get_manager(user_id)
        direct_raw = self.get_direct_groups(user_id)
        transitive_raw = self.get_transitive_groups(user_id)

        groups_complete = direct_raw is not None and transitive_raw is not None
        direct_raw = direct_raw or []
        transitive_raw = transitive_raw or []

        direct_ids = {
            str(item.get("id"))
            for item in direct_raw
            if item.get("id")
        }
        nested_raw = [
            item
            for item in transitive_raw
            if str(item.get("id")) not in direct_ids
        ]

        direct_groups = [
            self._normalize_group(item, "Direct")
            for item in direct_raw
        ]
        nested_groups = [
            self._normalize_group(item, "Nested")
            for item in nested_raw
        ]
        direct_groups.sort(
            key=lambda item: str(item.get("Name") or "").casefold()
        )
        nested_groups.sort(
            key=lambda item: str(item.get("Name") or "").casefold()
        )

        effective_by_id: Dict[str, Dict[str, Any]] = {}
        for group in direct_groups + nested_groups:
            key = str(
                group.get("GraphId")
                or group.get("Name")
                or ""
            ).casefold()
            if key and key not in effective_by_id:
                effective_by_id[key] = group

        effective_groups = sorted(
            effective_by_id.values(),
            key=lambda item: str(item.get("Name") or "").casefold(),
        )

        phones = user.get("businessPhones")
        office_phone = (
            phones[0]
            if isinstance(phones, list) and phones
            else None
        )
        policies = str(user.get("passwordPolicies") or "")

        return {
            "Success": True,
            "Name": user.get("displayName"),
            "DisplayName": user.get("displayName"),
            "GivenName": user.get("givenName"),
            "Surname": user.get("surname"),
            "SamAccountName": user.get("onPremisesSamAccountName"),
            "UserPrincipalName": user.get("userPrincipalName"),
            "Enabled": user.get("accountEnabled"),
            "LockedOut": None,
            "LockedOutFromGetADUser": None,
            "LockedOutFromSearchADAccount": None,
            "LockoutStatusSource": (
                "Unavailable from Microsoft Graph. Use the PowerShell "
                "backend for current Active Directory lockout status."
            ),
            "LockoutTime": None,
            "BadPasswordCount": None,
            "LastBadPasswordTime": None,
            "LastBadPasswordAttempt": None,
            "PasswordExpired": None,
            "PasswordLastSet": user.get("lastPasswordChangeDateTime"),
            "PasswordNeverExpires": (
                "DisablePasswordExpiration" in policies
            ),
            "CannotChangePassword": None,
            "PasswordNotRequired": None,
            "AccountExpirationDate": None,
            "LastLogonDate": None,
            "DistinguishedName": user.get(
                "onPremisesDistinguishedName"
            ),
            "CanonicalName": None,
            "Mail": user.get("mail") or user.get("userPrincipalName"),
            "Department": user.get("department"),
            "JobTitle": user.get("jobTitle"),
            "Office": user.get("officeLocation"),
            "OfficePhone": office_phone,
            "MobilePhone": user.get("mobilePhone"),
            "EmployeeID": user.get("employeeId"),
            "EmployeeNumber": None,
            "Description": None,
            "Manager": manager.get("manager_id"),
            "ManagerAssigned": bool(manager.get("manager_id")),
            "ManagerName": manager.get("manager_name"),
            "ManagerDisplayName": manager.get("manager_name"),
            "ManagerSamAccountName": manager.get(
                "manager_sam_account_name"
            ),
            "ManagerUserPrincipalName": manager.get(
                "manager_user_principal_name"
            ),
            "ManagerEmail": manager.get("manager_email"),
            "ManagerJobTitle": manager.get("manager_job_title"),
            "ManagerDepartment": manager.get("manager_department"),
            "ManagerDistinguishedName": None,
            "ManagerEnabled": manager.get("manager_enabled"),
            "ManagerResolutionError": None,
            "PrimaryGroupName": None,
            "PrimaryGroups": [],
            "DirectGroupMembershipCount": len(direct_groups),
            "NestedGroupMembershipCount": len(nested_groups),
            "EffectiveGroupMembershipCount": len(effective_groups),
            "DirectGroupNames": [
                item.get("Name")
                for item in direct_groups
                if item.get("Name")
            ],
            "NestedGroupNames": [
                item.get("Name")
                for item in nested_groups
                if item.get("Name")
            ],
            "EffectiveGroupNames": [
                item.get("Name")
                for item in effective_groups
                if item.get("Name")
            ],
            "DirectGroups": direct_groups,
            "NestedGroups": nested_groups,
            "EffectiveGroups": effective_groups,
            "GroupMembershipLookupComplete": groups_complete,
            "WhenCreated": user.get("createdDateTime"),
            "WhenChanged": user.get("onPremisesLastSyncDateTime"),
            "Domain": user.get("onPremisesDomainName"),
            "DomainController": None,
            "ExecutionIdentity": "Microsoft Graph application",
            "ExecutionComputer": None,
            "GraphUserId": user_id,
            "OnPremisesSyncEnabled": user.get(
                "onPremisesSyncEnabled"
            ),
            "EmployeeType": user.get("employeeType"),
            "CompanyName": user.get("companyName"),
            "UserType": user.get("userType"),
            "GraphUnavailableFields": [
                "LockedOut",
                "LockoutTime",
                "BadPasswordCount",
                "LastBadPasswordAttempt",
                "PasswordExpired",
                "CanonicalName",
                "PrimaryGroupName",
                "Exact nested-group inheritance path",
            ],
        }

    def change_password(self, user_id: str, new_password: str) -> bool:
        """Set a user's password through the authentication methods API."""
        if not self._ensure_token():
            return False

        encoded = self._encoded_identifier(user_id)
        url = (
            f"{self.graph_api_url}/users/{encoded}/authentication/methods/"
            f"{self.PASSWORD_METHOD_ID}/resetPassword"
        )
        try:
            response = requests.post(
                url,
                headers=self._headers(),
                json={"newPassword": new_password},
                timeout=self.timeout_seconds,
                verify=self.verify_ssl,
            )
        except requests.RequestException as exc:
            logger.error(
                "Graph password reset request failed | type={}",
                type(exc).__name__,
            )
            return False

        if response.status_code not in (200, 202):
            self._log_graph_error(response, "Graph password reset")
            return False

        status_url = response.headers.get("Location")
        if status_url:
            return self._await_reset(status_url)
        return True

    def _await_reset(
        self,
        status_url: str,
        attempts: int = 6,
        interval: float = 3.0,
    ) -> bool:
        for attempt in range(attempts):
            time.sleep(interval)
            try:
                response = requests.get(
                    status_url,
                    headers=self._headers(),
                    timeout=self.timeout_seconds,
                    verify=self.verify_ssl,
                )
            except requests.RequestException:
                return True

            if response.status_code not in (200, 202):
                logger.warning(
                    "Unable to read password reset status; treating accepted "
                    "request as submitted"
                )
                return True

            try:
                status = str(response.json().get("status") or "").casefold()
            except ValueError:
                return True

            logger.debug(
                "Password reset status | attempt={} | status={}",
                attempt + 1,
                status,
            )
            if status == "succeeded":
                return True
            if status == "failed":
                return False

        logger.warning("Password reset is still in progress after polling")
        return True

    def reset_password(self, user_id: str) -> Optional[str]:
        temporary_password = self.generate_temp_password()
        if self.change_password(user_id, temporary_password):
            return temporary_password
        return None

    @staticmethod
    def generate_temp_password() -> str:
        consonants = "bdfghjklmnprstvwz"
        vowels = "aeiou"
        rng = secrets.SystemRandom()

        def syllables(count: int) -> str:
            return "".join(
                rng.choice(consonants) + rng.choice(vowels)
                for _ in range(count)
            )

        first = syllables(2).capitalize()
        second = syllables(2)
        digits = "".join(rng.choice("0123456789") for _ in range(7))
        return f"{first}{second}@{digits}$"
