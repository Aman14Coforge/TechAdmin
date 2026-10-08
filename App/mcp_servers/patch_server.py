from mcp.server.fastmcp import FastMCP
from App.tools.patch.tools import get_patch_report,run_patch_scan,raise_patch_ticket
mcp=FastMCP("techadmin-patch-server")
mcp.tool()(get_patch_report);mcp.tool()(run_patch_scan);mcp.tool()(raise_patch_ticket)
if __name__=="__main__":mcp.run(transport="stdio")
