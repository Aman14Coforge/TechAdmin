"""
LLM Prompts Module

Purpose:
    Store the controlled prompts used by TechAdmin for intent
    classification and metadata extraction.

Security:
    Passwords and authorization approval must never be extracted from
    natural-language requests. Those fields must be supplied through
    secure structured UI controls.
"""


_INTENT_RULES = """
Supported intents:

1. get_user_details
   Retrieve, inspect, show, find or look up a user account.

2. password_reset
   Reset, change, replace or recover a password.

3. account_unlock
   Unlock a locked Active Directory account.

4. grant_access
   Add a user to a group or grant access.

5. revoke_access
   Remove a user from a group or revoke access.

6. failed_login_investigation
   Investigate failed logins, authentication failures or account
   lockouts.

7. create_user
   Create, provision or onboard a new Active Directory user.

8. delete_user
   Delete, remove or deprovision an Active Directory user.

9. create_group
   Create a new Active Directory security group.

10. create_vm
    Create or provision a new Hyper-V virtual machine.

11. unknown
    The request does not match a supported TechAdmin operation.

Important classification rules:

- "Remove user from group" means revoke_access.
- "Delete user" or "delete account" means delete_user.
- "Add user to group" means grant_access.
- "Create group" means create_group, not grant_access.
- "Create VM", "new VM" and "provision virtual machine" mean create_vm.
- A request that only asks to see account information means
  get_user_details.
- Hardware, network, printer and software issues are unknown unless a
  corresponding supported intent is added later.
""".strip()


_METADATA_RULES = """
Extract only fields explicitly stated in the request.

Identity fields:

- username
- user_id
- email
- employee_number
- group_name
- time_window
- username_source

User-provisioning fields:

- first_name
- last_name
- department
- target_ou

Group-provisioning fields:

- description

Virtual-machine fields:

- target_host
- vm_name
- cpu_count
- ram_gb
- vswitch_name
- ip_address
- subnet
- gateway
- dns
- hostname
- domain
- domain_user

Rules:

- If a complete email address is supplied and username is absent,
  username may be the exact substring before @.
- Set username_source to derived_from_email only when that deterministic
  transformation is used.
- Set username_source to explicit when username is directly supplied.
- Do not convert an ordinary display name into a username.
- Do not invent values.
- Do not extract any password.
- Do not extract initial_password.
- Do not extract admin_password.
- Do not extract domain_password.
- Do not infer authorization approval.
- approval_granted must always be false in LLM output.
- cpu_count and ram_gb must be JSON integers when present.
- Use JSON null for every missing field.
""".strip()


_OUTPUT_RULES = """
Output rules:

- Return exactly one valid JSON object.
- Do not add Markdown.
- Do not add a think block.
- Do not add text before or after the JSON.
- confidence must be a JSON number from 0 to 1.
""".strip()


INTENT_CLASSIFICATION_PROMPT = (
    """
You are the intent-classification component of TechAdmin.

"""
    + _INTENT_RULES
    + """

"""
    + _OUTPUT_RULES
    + """

Return:

{{
    "intent": "<supported intent>",
    "confidence": 0.0,
    "explanation": "<brief reason>"
}}

User request:

{user_input}

JSON response:
"""
).strip()


METADATA_EXTRACTION_PROMPT = (
    """
You are the metadata-extraction component of TechAdmin.

Classified intent:

{intent}

"""
    + _METADATA_RULES
    + """

"""
    + _OUTPUT_RULES
    + """

Return:

{{
    "username": null,
    "user_id": null,
    "email": null,
    "employee_number": null,
    "group_name": null,
    "time_window": null,
    "username_source": null,
    "first_name": null,
    "last_name": null,
    "department": null,
    "target_ou": null,
    "description": null,
    "target_host": null,
    "vm_name": null,
    "cpu_count": null,
    "ram_gb": null,
    "vswitch_name": null,
    "ip_address": null,
    "subnet": null,
    "gateway": null,
    "dns": null,
    "hostname": null,
    "domain": null,
    "domain_user": null,
    "approval_granted": false
}}

User request:

{user_input}

JSON response:
"""
).strip()


UNIFIED_EXTRACTION_PROMPT = (
    """
You are the unified intent-classification and metadata-extraction
component of TechAdmin.

Classify the request and extract the available metadata in one response.

"""
    + _INTENT_RULES
    + """

"""
    + _METADATA_RULES
    + """

"""
    + _OUTPUT_RULES
    + """

Return exactly this structure:

{{
    "intent": "<supported intent>",
    "confidence": 0.0,
    "explanation": "<brief reason>",
    "metadata": {{
        "username": null,
        "user_id": null,
        "email": null,
        "employee_number": null,
        "group_name": null,
        "time_window": null,
        "username_source": null,
        "first_name": null,
        "last_name": null,
        "department": null,
        "target_ou": null,
        "description": null,
        "target_host": null,
        "vm_name": null,
        "cpu_count": null,
        "ram_gb": null,
        "vswitch_name": null,
        "ip_address": null,
        "subnet": null,
        "gateway": null,
        "dns": null,
        "hostname": null,
        "domain": null,
        "domain_user": null,
        "approval_granted": false
    }}
}}

Examples:

Request:
Create a security group named App-Support with description Application
support team

Response:
{{
    "intent": "create_group",
    "confidence": 0.98,
    "explanation": "Requests creation of an AD security group.",
    "metadata": {{
        "username": null,
        "user_id": null,
        "email": null,
        "employee_number": null,
        "group_name": "App-Support",
        "time_window": null,
        "username_source": null,
        "first_name": null,
        "last_name": null,
        "department": null,
        "target_ou": null,
        "description": "Application support team",
        "target_host": null,
        "vm_name": null,
        "cpu_count": null,
        "ram_gb": null,
        "vswitch_name": null,
        "ip_address": null,
        "subnet": null,
        "gateway": null,
        "dns": null,
        "hostname": null,
        "domain": null,
        "domain_user": null,
        "approval_granted": false
    }}
}}

Request:
Add alex.lee to VPN-Users

Response:
{{
    "intent": "grant_access",
    "confidence": 0.98,
    "explanation": "Requests adding a user to an AD group.",
    "metadata": {{
        "username": "alex.lee",
        "user_id": null,
        "email": null,
        "employee_number": null,
        "group_name": "VPN-Users",
        "time_window": null,
        "username_source": "explicit",
        "first_name": null,
        "last_name": null,
        "department": null,
        "target_ou": null,
        "description": null,
        "target_host": null,
        "vm_name": null,
        "cpu_count": null,
        "ram_gb": null,
        "vswitch_name": null,
        "ip_address": null,
        "subnet": null,
        "gateway": null,
        "dns": null,
        "hostname": null,
        "domain": null,
        "domain_user": null,
        "approval_granted": false
    }}
}}

Request:
Provision VM APP-SRV-01 on HVHOST01 with 4 CPUs, 16 GB RAM,
virtual switch ProductionSwitch and hostname APP-SRV-01

Response:
{{
    "intent": "create_vm",
    "confidence": 0.98,
    "explanation": "Requests provisioning of a Hyper-V VM.",
    "metadata": {{
        "username": null,
        "user_id": null,
        "email": null,
        "employee_number": null,
        "group_name": null,
        "time_window": null,
        "username_source": null,
        "first_name": null,
        "last_name": null,
        "department": null,
        "target_ou": null,
        "description": null,
        "target_host": "HVHOST01",
        "vm_name": "APP-SRV-01",
        "cpu_count": 4,
        "ram_gb": 16,
        "vswitch_name": "ProductionSwitch",
        "ip_address": null,
        "subnet": null,
        "gateway": null,
        "dns": null,
        "hostname": "APP-SRV-01",
        "domain": null,
        "domain_user": null,
        "approval_granted": false
    }}
}}

User request:

{user_input}

JSON response:
"""
).strip()