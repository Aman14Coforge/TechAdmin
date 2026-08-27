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

print("\n" + "=" * 80)
print("VERIFICATION RESULT")
print("=" * 80)

all_set = all([client_id, client_secret, tenant_id])
if all_set:
    print("✅ ALL CREDENTIALS ARE SET!")
    print("\nNow testing authentication...")
    
    from App.integration.microsoft_graph import MicrosoftGraphClient
    
    client = MicrosoftGraphClient()
    
    print(f"\nClient ID in object: {client.client_id[:8]}...{client.client_id[-8:]}")
    print(f"Tenant ID in object: {client.tenant_id}")
    print(f"Token URL: {client.token_url}")
    
    print("\nAttempting authentication...")
    if client.authenticate():
        print("✅ AUTHENTICATION SUCCESSFUL!")
        print(f"Access token obtained: {len(client.access_token)} chars")
        print(f"Token preview: {client.access_token}...")
    else:
        print("❌ AUTHENTICATION FAILED!")
        print("Check if app has correct permissions in Azure AD")
else:
    print("❌ CREDENTIALS NOT SET!")
    if not client_id:
        print("  - GRAPH_CLIENT_ID is missing")
    if not client_secret:
        print("  - GRAPH_CLIENT_SECRET is missing")
    if not tenant_id:
        print("  - GRAPH_TENANT_ID is missing")

print("\n" + "=" * 80)
