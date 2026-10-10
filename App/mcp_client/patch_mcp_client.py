"""Typed stdio MCP client for TechAdmin patch tools."""
from __future__ import annotations
import asyncio,json,os,sys
from datetime import date
from pathlib import Path
from typing import Any
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client

class PatchMCPClient:
    def __init__(self)->None:
        self.server=StdioServerParameters(command=sys.executable,args=["-m","App.mcp_servers.patch_server"],env=os.environ.copy(),cwd=str(Path(__file__).resolve().parents[2]))
    async def call_tool(self,name:str,arguments:dict[str,Any]|None=None)->dict[str,Any]:
        async with stdio_client(self.server) as (read,write):
            async with ClientSession(read,write) as session:
                await session.initialize();response=await session.call_tool(name,arguments or {},read_timeout_seconds=240.0)
        if getattr(response,"isError",False):
            detail=self._text(response)
            structured=getattr(response,"structuredContent",None)
            if isinstance(structured,dict):
                detail=detail or str(structured.get("error") or structured.get("message") or structured)
            if detail:
                try:
                    parsed=json.loads(detail)
                    if isinstance(parsed,dict):detail=str(parsed.get("error") or parsed.get("message") or detail)
                except json.JSONDecodeError:
                    pass
            raise RuntimeError(f"MCP tool {name} failed: {detail or 'server returned an error without details'}")
        text=self._text(response)
        if not text:
            structured=getattr(response,"structuredContent",None)
            if isinstance(structured,dict):return structured
        if not text:return {}
        try:return json.loads(text)
        except json.JSONDecodeError:return {"success":True,"message":text}
    @staticmethod
    def _text(response)->str:
        parts=[]
        for item in getattr(response,"content",[]) or []:
            value=getattr(item,"text",None)
            if value:parts.append(value)
        return "\n".join(parts)
    @staticmethod
    def run(coro):
        try:asyncio.get_running_loop()
        except RuntimeError:pass
        else:
            coro.close()
            raise RuntimeError("PatchMCPClient synchronous methods require no active event loop.")
        try:
            return asyncio.run(coro)
        except ExceptionGroup as exc:
            def leaves(error):
                if isinstance(error, BaseExceptionGroup):
                    return [leaf for child in error.exceptions for leaf in leaves(child)]
                return [f"{type(error).__name__}: {error}"]
            raise RuntimeError("Patch MCP failed: " + "; ".join(leaves(exc))) from exc
    def device_report(self,device_name:str,report_date:date|None=None)->dict[str,Any]:return self.run(self.call_tool("generate_patch_device_report",{"device_name":device_name,"report_date":report_date.isoformat() if report_date else None}))
    def fleet_report(self,report_date:date)->dict[str,Any]:return self.run(self.call_tool("generate_patch_fleet_report",{"report_date":report_date.isoformat()}))
    def selected_report(self,device_names:list[str],report_date:date)->dict[str,Any]:return self.run(self.call_tool("generate_selected_devices_report",{"device_names":device_names,"report_date":report_date.isoformat()}))
    def raise_tickets(self,device_names:list[str],*,reason:str,requested_by:str)->dict[str,Any]:return self.run(self.call_tool("raise_patch_ticket",{"device_names":device_names,"reason":reason,"confirmed":True,"requested_by":requested_by}))
