"""Smoke test for the actual stage-by-stage TechAdmin LangGraph."""
from __future__ import annotations
import json, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT))
from dotenv import load_dotenv
load_dotenv(ROOT/'.env',override=False)
from App.workflow.graph import TechAdminWorkflow
workflow=TechAdminWorkflow()
print(workflow.draw_mermaid())
result=workflow.invoke(
    user_input="Get user details for MigrationTest2@Coforge.com",
    request_id="langgraph_smoke_test",
    correlation_id="corr_langgraph_smoke_test",
    confirmed=False,
    requester_id="langgraph_test",
    requester_role="helpdesk",
)
print(json.dumps({
    "success":result.get("success"),
    "intent":result.get("intent"),
    "orchestration":result.get("orchestration"),
},indent=2))
