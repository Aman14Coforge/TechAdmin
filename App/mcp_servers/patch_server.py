from mcp.server.mcpserver import MCPServer
from App.tools.patch.tools import generate_patch_device_report,generate_patch_fleet_report,generate_selected_devices_report,get_patch_report,raise_patch_ticket,run_patch_scan
mcp=MCPServer("techadmin-patch-server")
for tool in (get_patch_report,run_patch_scan,generate_patch_device_report,generate_patch_fleet_report,generate_selected_devices_report,raise_patch_ticket):mcp.tool()(tool)
if __name__=="__main__":mcp.run(transport="stdio")
