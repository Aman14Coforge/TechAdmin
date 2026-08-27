# TechAdmin Flow - Quick Reference Card for Team

## 🎯 What's Ready

A **complete, working end-to-end flow** with real Microsoft Graph API integration.

```
User Query
    ↓
Ollama LLM (Intent) → get_user_details / password_reset
    ↓
Ollama LLM (Metadata) → {"email": "user@company.com"}
    ↓
Router → identity_agent
    ↓
Identity Agent → Tool Selection
    ├─ GetUserDetailsTool ✅ WORKING
    └─ PasswordResetTool ✅ WORKING
        ↓
    Microsoft Graph API (REAL CALLS)
        ↓
    Formatted Response ✅
```

## 📝 Quick Start

### 1. Setup (Do Once)
```bash
# Install deps
pip install -r requirements.txt

# Start Ollama
ollama run qwen3:14b

# Configure .env with your Azure AD creds
```

### 2. Run Demo
```bash
python Scripts/demo_flow.py
```

### 3. Try These Queries
- `Get details for derhant@coforge.com` → Returns user info from Graph API
- `Find user xyz` → Searches by username
- `Reset password for user123` → Resets password

## 📂 Files to Review (In Order)

### For Everyone
1. **`Scripts/demo_flow.py`** - Complete working example (Start here!)
2. **`Scripts/DEMO_README.md`** - How to run the demo

### For Each Team Member

**Amit (Intent & Metadata)**
- See: `App/intent/classifier.py` + `metadata_extractor.py`
- Uses: `App/intent/prompts.py` 
- Status: ✅ Ready with Ollama

**Shreesanyog (Workflow & Routing)**
- See: `App/workflow/router.py` + `formatter.py`
- Integration point: Wrap demo flow in LangGraph
- Status: ✅ Core logic ready

**Aman Mishra (Graph API)**
- See: `App/integration/microsoft_graph.py` (FULLY IMPLEMENTED!)
- See: `App/tools/identity/get_user_details.py` (NEW)
- See: `App/tools/identity/reset_password.py` (UPDATED)
- Status: ✅ Working with real API calls

**Roshan (FastAPI & Testing)**
- See: `App/apis/routes.py` (skeleton ready)
- Integration: Wire demo flow into `/api/v1/request` endpoint
- Status: ✅ Can use demo as reference

## 🔧 Implementation Pattern (Reference)

```python
# Step 1: Create Tool
class MyTool:
    def execute(self, input) -> Dict:
        try:
            result = api_call(input)
            return {"success": True, "result": result}
        except Exception as e:
            return {"success": False, "error": str(e)}

# Step 2: Use in Agent
class MyAgent:
    def execute(self, operation, metadata):
        if operation == "my_op":
            tool = MyTool()
            return tool.execute(metadata)

# Step 3: Test with Demo Flow
response = demo.execute_flow("my query")
```

## 🧪 Testing Workflow

```
1. python Scripts/demo_flow.py
2. Enter query (or pick example)
3. Review output:
   - Intent classification ✅
   - Metadata extraction ✅
   - Agent routing ✅
   - Tool execution ✅
   - Response formatting ✅
4. Check logs/techadmin.log for details
5. Understand the flow
6. Implement your module
```

## 📊 What Works Right Now

| Component | Status | Test |
|-----------|--------|------|
| Graph API Auth | ✅ | Check logs for token |
| Get User Details | ✅ | `Get details for user@email.com` |
| Reset Password | ✅ | `Reset password for username` |
| Intent Classification | ✅ | Runs with Ollama |
| Metadata Extraction | ✅ | Runs with Ollama |
| Agent Routing | ✅ | Routes correctly |
| Response Formatting | ✅ | User-friendly output |

## 🎓 Learning Path

1. **Day 1:** Run demo, understand flow
2. **Day 2:** Review code for your module
3. **Day 3:** Implement your module following the pattern
4. **Day 4:** Test your module with demo flow
5. **Day 5:** Integrate into complete system

## 🔗 Integration Points

**Shreesanyog (Wrap in LangGraph)**
```python
# Current: demo_flow.py calls functions sequentially
# Future: Wrap in LangGraph StateGraph
# Reference: See App/workflow/state.py for WorkflowState schema
```

**Roshan (Wire into FastAPI)**
```python
# Current: demo_flow.py is standalone script
# Future: Move logic into submit_request() in App/apis/routes.py
# API Endpoint: POST /api/v1/request
```

## 📞 Questions

- "Why does it work?" → Check logs/techadmin.log
- "What's the response format?" → See Scripts/demo_flow.py output
- "How do I extend it?" → Follow the pattern above
- "How do I test my module?" → Use demo_flow as reference

## ✨ Next Steps

```
Amit → Enhance prompts
    ↓
Shreesanyog → Integrate LangGraph
    ↓
Aman M → Add more Graph API operations
    ↓
Roshan → Wire into FastAPI
    ↓
All → Full testing and validation
```

---

**TL;DR:** Run `python Scripts/demo_flow.py` to see complete working flow. Use as reference for your module.
