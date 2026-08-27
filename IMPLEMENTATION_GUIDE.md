"""
Implementation Guide for TechAdmin Agent Platform v1
Author: Aman Gupta (Tech Lead)
Date: 2026-08-27
Status: DRAFT - Ready for Team Implementation
"""

## Current Status
✅ Project Structure: COMPLETE
✅ Placeholder Files: CREATED
✅ Module Ownership: ASSIGNED
🔄 Implementation: READY TO START

---

## Team Implementation Tasks

### Module 1: Intent Classification & Metadata Extraction
**Owner:** Amit Bhagat (AI Engineer)
**Files:** 
- `App/intent/classifier.py` - IntentClassifier class
- `App/intent/metadata_extractor.py` - MetadataExtractor class
- `App/intent/prompts.py` - LLM prompts

**Tasks:**
1. [ ] Implement IntentClassifier.classify() method
   - Initialize OllamaLLM with OLLAMA_HOST from config
   - Use INTENT_CLASSIFICATION_PROMPT from prompts.py
   - Parse JSON response from LLM
   - Return intent, confidence, and explanation

2. [ ] Implement MetadataExtractor.extract() method
   - Initialize OllamaLLM
   - Use METADATA_EXTRACTION_PROMPT with intent context
   - Extract: username, user_id, email, employee_number
   - Parse JSON response from LLM
   - Return validated metadata

3. [ ] Implement MetadataExtractor.validate_metadata() method
   - Validate required fields based on intent
   - For password_reset: username is mandatory
   - Return validation status and error messages

4. [ ] Create unit tests in `Tests/test_intent.py`
   - Test various intent types
   - Test metadata extraction
   - Test validation rules
   - Test error cases

---

### Module 2: Workflow Orchestration & Agent Framework
**Owner:** Shreesanyog (AI Engineer)
**Files:**
- `App/workflow/graph.py` - LangGraph workflow
- `App/workflow/state.py` - Workflow state schema
- `App/workflow/router.py` - Request router
- `App/workflow/formatter.py` - Response formatter

**Tasks:**
1. [ ] Implement TechAdminWorkflow.build_graph() method
   - Create StateGraph with WorkflowState
   - Add node for intent classification
   - Add node for metadata extraction
   - Add node for validation
   - Add node for routing
   - Add conditional edges based on intent/agent
   - Add node for response formatting
   - Compile and return graph

2. [ ] Implement TechAdminWorkflow.execute() method
   - Initialize workflow graph
   - Create initial state from user_input
   - Execute graph with invoke()
   - Handle errors and exceptions
   - Return formatted result

3. [ ] Implement AgentRouter.route() method
   - Map intent to agent type
   - Validate metadata before routing
   - Return routing information
   - Handle unsupported intents

4. [ ] Enhance ResponseFormatter methods
   - Create response templates for each operation
   - Format success/failure messages
   - Include relevant details for user
   - Consider localization if needed

5. [ ] Create end-to-end tests in `Tests/test_agent.py`

---

### Module 3: API Integration & Microsoft Graph
**Owner:** Aman Mishra (IT Developer)
**Files:**
- `App/integration/microsoft_graph.py` - Graph API client
- `App/tools/identity/reset_password.py` - Password reset tool

**Tasks:**
1. [ ] Implement MicrosoftGraphClient class
   - Implement authenticate() for OAuth2 client credentials flow
   - Use GRAPH_CLIENT_ID, GRAPH_CLIENT_SECRET, GRAPH_TENANT_ID from config
   - Get and store access token
   - Initialize msgraph-core client

2. [ ] Implement MicrosoftGraphClient methods
   - find_user_by_username(): Query /users endpoint with filter
   - change_password(): Call /users/{id}/changePassword endpoint
   - reset_password(): Generate temporary password and reset

3. [ ] Implement GraphAPIPasswordResetTool class
   - Initialize with Azure AD credentials
   - Implement reset_password() method
   - Call Graph API to find user
   - Generate temporary password
   - Set password and mark for change on next login
   - Return result with temporary password

4. [ ] Implement validation methods
   - Validate username format
   - Check if user exists in AD
   - Handle API errors gracefully

5. [ ] Create integration tests
   - Test Graph API authentication
   - Test user lookup
   - Test password reset (use test account)
   - Test error handling

---

### Module 4: FastAPI & Testing
**Owner:** Roshan (IT Developer)
**Files:**
- `App/main.py` - FastAPI entry point (COMPLETE)
- `App/apis/routes.py` - API routes (COMPLETE)
- `App/apis/schemas.py` - Pydantic schemas (COMPLETE)
- `Tests/test_api.py` - API tests

**Tasks:**
1. [ ] Implement submit_request() endpoint
   - Generate request_id if not provided
   - Call IntentClassifier
   - Call MetadataExtractor
   - Call AgentRouter
   - Execute workflow
   - Format and return response
   - Handle errors with proper HTTP status codes

2. [ ] Verify health_check() endpoint works

3. [ ] Enhance error handling
   - Validate request schemas
   - Return proper HTTP status codes
   - Include error details in response

4. [ ] Implement comprehensive API tests
   - Test health endpoint
   - Test password reset request
   - Test invalid requests
   - Test error responses
   - Test end-to-end flow

5. [ ] Setup logging in main.py
   - Configure structured logging
   - Log all requests/responses
   - Track request lifecycle

---

## Dependencies to Install

The following are already in requirements.txt and need to be installed:

```bash
pip install -r requirements.txt
```

Key packages:
- fastapi, uvicorn - REST API framework
- langgraph, langchain, langchain-ollama - LLM orchestration
- pydantic - Data validation
- python-dotenv, pyyaml - Configuration
- loguru - Logging
- requests, httpx - HTTP calls
- msgraph-core - Microsoft Graph API (may need to add)

## Configuration Files to Update

1. **`.env`** - Add missing variables:
   ```
   GRAPH_CLIENT_ID=<your_azure_app_id>
   GRAPH_CLIENT_SECRET=<your_azure_app_secret>
   GRAPH_TENANT_ID=<your_azure_tenant_id>
   API_HOST=0.0.0.0
   API_PORT=8000
   ```

2. **`Configs/llm_config.yaml`** - Verify model configuration
   ```yaml
   llm:
     model_name: qwen3:14b
     host: http://localhost:11434
   ```

3. **`Configs/intent_mapping.yaml`** - TODO: Create
   ```yaml
   intents:
     password_reset:
       description: "Reset user password"
       required_metadata:
         - username
     account_unlock:
       description: "Unlock user account"
       required_metadata:
         - username
   ```

---

## Testing & Validation

### Manual Testing Flow
1. Start Ollama: `ollama run qwen3:14b`
2. Start FastAPI: `python -m App.main`
3. Test endpoint:
   ```bash
   curl -X POST "http://localhost:8000/api/v1/request" \
     -H "Content-Type: application/json" \
     -d '{"user_input": "Reset password for aman.gupta"}'
   ```

### Unit Testing
```bash
pytest Tests/ -v
```

### Integration Testing
- Test with real Ollama instance
- Test with Azure AD sandbox environment
- Test end-to-end workflow

---

## Deployment Checklist

- [ ] All unit tests passing
- [ ] All integration tests passing
- [ ] Code review completed
- [ ] Documentation updated
- [ ] Error handling verified
- [ ] Logging configured
- [ ] Security review (auth, secrets management)
- [ ] Performance testing
- [ ] Production config prepared

---

## Next Steps (Post v1.0)

- [ ] Add Account Unlock operation
- [ ] Add Network Agent (Guest WiFi, Connectivity)
- [ ] Add Patch Agent (Software Install, Patch Management)
- [ ] Implement Teams/Copilot integration
- [ ] Add audit logging
- [ ] Add request tracking dashboard
- [ ] Implement approval workflows
- [ ] Add multi-tenancy support

---

## Questions & Notes

**For Amit Bhagat (Intent & Metadata):**
- Need prompt templates for other intents? Ask Shreesanyog
- Confidence threshold recommendation? Default 0.8?

**For Shreesanyog (Workflow & Agent):**
- LangGraph version preference? Latest stable?
- Error recovery strategy for failed operations?

**For Aman Mishra (Graph API):**
- Which Graph API version? v1.0 or beta?
- Temporary password generation strategy?
- User notification preference?

**For Roshan (FastAPI & Testing):**
- Rate limiting needed? Recommended?
- API versioning strategy?
- Monitoring/metrics to track?

---

## Success Criteria for v1.0

✅ Intent classification works for password_reset (>90% accuracy)
✅ Metadata extraction identifies username correctly
✅ Password reset API successfully calls Microsoft Graph
✅ Proper error handling for all failure scenarios
✅ Unit tests with >80% code coverage
✅ Integration tests passing
✅ End-to-end workflow working
✅ API documentation complete
✅ Team trained and ready for v1.1

---

Last Updated: 2026-08-27
Status: READY FOR IMPLEMENTATION
