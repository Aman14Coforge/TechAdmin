# TechAdmin Pydantic Tool Routing
All runtime contracts, graph state, LLM output, validation, tool input and tool output use Pydantic. LangGraph node update dictionaries are framework-required state updates; LangGraph validates them against `WorkflowState` before downstream nodes.

Tools intentionally contain no enterprise API call. Each logs `TOOL_CALL` and returns a Pydantic `ToolResult(status=not_implemented)` with an operation ID. Replace only the TODO in `App/agents/tools/common.py` or split provider adapters later.
