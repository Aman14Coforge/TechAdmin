from __future__ import annotations
from mcp.server import MCPServer
from App.tools.identity.directory_operations import DirectoryOperationsTool
from App.workflow.state import IdentityMetadata, IntentType, ToolRequest

mcp = MCPServer("techadmin-directory-operations")


def _execute(intent: IntentType, request_id: str, correlation_id: str, metadata: dict) -> dict:
    request = ToolRequest(request_id=request_id, correlation_id=correlation_id, intent=intent, metadata=IdentityMetadata.model_validate(metadata))
    return DirectoryOperationsTool().execute(request).model_dump(mode="json")


@mcp.tool()
def create_user(request_id: str, correlation_id: str, first_name: str, last_name: str, username: str, email: str, department: str, initial_password: str, target_ou: str | None = None) -> dict:
    """Create and enable an Active Directory user using the approved script."""
    return _execute(IntentType.CREATE_USER, request_id, correlation_id, locals() | {"email": email})


@mcp.tool()
def delete_user(request_id: str, correlation_id: str, first_name: str, last_name: str, username: str, approval_granted: bool) -> dict:
    """Delete an Active Directory user after identity verification and explicit approval."""
    return _execute(IntentType.DELETE_USER, request_id, correlation_id, locals())


@mcp.tool()
def create_group(request_id: str, correlation_id: str, group_name: str, description: str | None = None) -> dict:
    """Create an Active Directory security group."""
    return _execute(IntentType.CREATE_GROUP, request_id, correlation_id, locals())


@mcp.tool()
def create_vm(request_id: str, correlation_id: str, target_host: str, vm_name: str, cpu_count: int, ram_gb: int, vswitch_name: str, hostname: str, admin_password: str, ip_address: str | None = None, subnet: str | None = None, gateway: str | None = None, dns: str | None = None, domain: str | None = None, domain_user: str | None = None, domain_password: str | None = None) -> dict:
    """Provision a Hyper-V VM using the approved script."""
    return _execute(IntentType.CREATE_VM, request_id, correlation_id, locals())


if __name__ == "__main__":
    mcp.run()
