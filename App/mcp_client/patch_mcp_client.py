import os,sys
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client
class PatchMCPClient:
 def __init__(self):self.server=StdioServerParameters(command=sys.executable,args=["-m","App.mcp_servers.patch_server"],env=os.environ.copy())
 async def call_tool(self,name,arguments=None):
  async with stdio_client(self.server) as (r,w):
   async with ClientSession(r,w) as s:await s.initialize();return await s.call_tool(name,arguments or {})
