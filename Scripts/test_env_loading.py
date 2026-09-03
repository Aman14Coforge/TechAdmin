"""
Test Script - Verify .env Loading
Purpose: Check if credentials are being read from .env file
"""

import sys
import os
from pathlib import Path
from dotenv import load_dotenv

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Load environment variables
load_dotenv()

print("=" * 80)
print("ENVIRONMENT VARIABLES VERIFICATION")
print("=" * 80)

# Check if .env file exists
env_file = project_root / ".env"
print(f"\n.env file path: {env_file}")
print(f".env exists: {env_file.exists()}")

print("\n" + "=" * 80)
print("CREDENTIALS FROM ENVIRONMENT")
print("=" * 80)

# Display credentials (masking sensitive data)
client_id = os.getenv("GRAPH_CLIENT_ID")
client_secret = os.getenv("GRAPH_CLIENT_SECRET")
tenant_id = os.getenv("GRAPH_TENANT_ID")

print(f"\nGRAPH_CLIENT_ID: {client_id if client_id else 'NOT SET ❌'}")
if client_id:
    print(f"  Length: {len(client_id)} chars")
    print(f"  Masked: {client_id[:8]}...{client_id[-8:]}")

print(f"\nGRAPH_CLIENT_SECRET: {client_secret if client_secret else 'NOT SET ❌'}")
if client_secret:
    print(f"  Length: {len(client_secret)} chars")
    print(f"  Masked: {client_secret[:8]}...{client_secret[-8:]}")

print(f"\nGRAPH_TENANT_ID: {tenant_id if tenant_id else 'NOT SET ❌'}")
if tenant_id:
    print(f"  Length: {len(tenant_id)} chars")

auth_mode = os.getenv("GRAPH_AUTH_MODE", "delegated")
graph_username = os.getenv("GRAPH_USERNAME")
graph_password = os.getenv("GRAPH_PASSWORD")

print(f"\nGRAPH_AUTH_MODE: {auth_mode}")
print(f"GRAPH_USERNAME: {graph_username if graph_username else 'NOT SET ❌'}")
print(f"GRAPH_PASSWORD: {'SET (' + str(len(graph_password)) + ' chars)' if graph_password else 'NOT SET ❌'}")

print("\n" + "=" * 80)
print("VERIFICATION RESULT")
print("=" * 80)

if auth_mode == "delegated":
    all_set = all([client_id, tenant_id, graph_username, graph_password])
else:
    all_set = all([client_id, client_secret, tenant_id])

if all_set:
    print("✅ ALL CREDENTIALS ARE SET!")
    print("\nNow testing authentication...")
    
    from App.integration.microsoft_graph import MicrosoftGraphClient
    
    client = MicrosoftGraphClient()
    
    print(f"\nClient ID in object: {client.client_id[:8]}...{client.client_id[-8:]}")
    print(f"Tenant ID in object: {client.tenant_id}")
    print(f"Auth mode: {client.auth_mode}")
    print(f"Token URL: {client.token_url}")
    
    print("\nAttempting authentication...")
    if client.authenticate():
        print("✅ AUTHENTICATION SUCCESSFUL!")
        print(f"Access token obtained: {len(client.access_token)} chars")
        
        test_user = graph_username
        print(f"\nTesting user lookup for: {test_user}")
        user = client.get_user_details(test_user)
        if user:
            print("✅ GRAPH API CALL SUCCESSFUL!")
            print(user)
        else:
            print("❌ GRAPH API CALL FAILED - see error above")
    else:
        print("❌ AUTHENTICATION FAILED!")
        print("Check credentials and app permissions in Azure AD")
else:
    print("❌ CREDENTIALS NOT SET!")
    if not client_id:
        print("  - GRAPH_CLIENT_ID is missing")
    if not tenant_id:
        print("  - GRAPH_TENANT_ID is missing")
    if auth_mode == "delegated":
        if not graph_username:
            print("  - GRAPH_USERNAME is missing")
        if not graph_password:
            print("  - GRAPH_PASSWORD is missing")
    elif not client_secret:
        print("  - GRAPH_CLIENT_SECRET is missing")

print("\n" + "=" * 80)
