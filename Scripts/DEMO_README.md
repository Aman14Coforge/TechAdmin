# TechAdmin Demo Flow - Quick Start Guide

## Overview
This is a complete end-to-end demo of the TechAdmin Agent Platform that tests the entire flow:
1. **Intent Classification** - Identifies what the user wants
2. **Metadata Extraction** - Extracts relevant information (username, email, etc.)
3. **Agent Routing** - Routes to the appropriate agent
4. **Agent Execution** - Executes the operation (e.g., get user details)
5. **Response Formatting** - Formats the result for the user

## Prerequisites

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

**Key packages needed:**
- `requests` - For HTTP calls to Microsoft Graph API
- `loguru` - For structured logging
- `langchain-ollama` - For LLM integration
- `pydantic` - For data validation
- `python-dotenv` - For environment variables
- `pyyaml` - For config file parsing

### 2. Setup Ollama
```bash
# Make sure Ollama is running
ollama run qwen3:14b
```

This provides the LLM for intent classification and metadata extraction.

### 3. Configure Environment Variables

Create/update `.env` file in the project root with your Azure AD credentials:

```env
# Ollama Configuration
OLLAMA_HOST=http://localhost:11434
MODEL_NAME=qwen3:14b

# API Configuration
API_TIMEOUT=60
LOG_LEVEL=INFO

# Microsoft Graph API Configuration
GRAPH_CLIENT_ID=your_azure_app_id
GRAPH_CLIENT_SECRET=your_azure_app_secret
GRAPH_TENANT_ID=your_azure_tenant_id
```

### 4. Get Your Azure AD Credentials

1. Go to [Azure Portal](https://portal.azure.com)
2. Navigate to **Azure Active Directory** → **App registrations**
3. Click **New registration**
4. Name it "TechAdmin" and click Register
5. Copy the **Application (client) ID** → Use as `GRAPH_CLIENT_ID`
6. Go to **Certificates & secrets** → **New client secret**
7. Copy the secret value → Use as `GRAPH_CLIENT_SECRET`
8. Copy your **Tenant ID** from the Overview page → Use as `GRAPH_TENANT_ID`

### 5. Grant API Permissions

1. In your app registration, go to **API permissions**
2. Click **Add a permission**
3. Select **Microsoft Graph** → **Application permissions**
4. Add these permissions:
   - `User.Read.All` - Read user details
   - `User.ManageIdentities.All` - For password reset (if needed)
5. Click **Grant admin consent**

## Running the Demo

### Interactive Mode
```bash
python Scripts/demo_flow.py
```

This will:
1. Validate your configuration
2. Show you example queries
3. Let you enter your own query
4. Execute the complete flow
5. Show detailed logs and results

### Example Queries

Try these queries:

1. **Get User Details (with email)**
   ```
   Get details for derhant@coforge.com
   ```

2. **Get User Details (with username)**
   ```
   Find user details for derhant
   ```

3. **Password Reset**
   ```
   Reset password for aman.gupta
   ```

4. **Natural Language Query**
   ```
   What is my account status
   ```

## Understanding the Output

The demo will show:

1. **Classification Step**
   - Identified intent
   - Confidence score

2. **Metadata Extraction**
   - Extracted fields (username, email, etc.)
   - Validation status

3. **Routing**
   - Selected agent type
   - Agent name

4. **Execution**
   - Tool execution results
   - API response data

5. **Final Response**
   - Formatted, user-friendly message
   - Success/failure status
   - Complete response JSON

## Troubleshooting

### Issue: "Cannot import module 'App...'"
**Solution:** Make sure you're running from the project root directory
```bash
cd d:\Projects\TechAdmin
python Scripts/demo_flow.py
```

### Issue: "Ollama connection refused"
**Solution:** Start Ollama first
```bash
ollama run qwen3:14b
```

### Issue: "Authentication failed with Microsoft Graph"
**Solution:** Check your Azure AD credentials:
- Verify CLIENT_ID, CLIENT_SECRET, TENANT_ID are correct
- Make sure the app has API permissions granted
- Check that you have admin consent

### Issue: "User not found"
**Solution:** 
- Make sure you're using the correct email or username
- Try with full email format: `username@domain.com`
- Verify the user exists in your Azure AD

## Testing Different Scenarios

### Scenario 1: Get User Details (Successful)
```
Query: "Get details for derhant@coforge.com"
Expected: Returns user ID, display name, email, account status
```

### Scenario 2: Get User Details (User Not Found)
```
Query: "Find user xyz123"
Expected: Returns error message that user doesn't exist
```

### Scenario 3: Password Reset
```
Query: "Reset password for aman.gupta"
Expected: Returns success message with temporary password (in logs)
```

## Code Flow for Reference

```
demo_flow.py (main entry)
    ↓
DemoFlow.execute_flow(user_input)
    ↓
[1] IntentClassifier.classify()
    - Uses Ollama LLM + prompts.py
    - Returns: {"intent": "...", "confidence": 0.95}
    ↓
[2] MetadataExtractor.extract()
    - Uses Ollama LLM + prompts.py
    - Returns: {"username": "...", "email": "..."}
    ↓
[3] AgentRouter.route()
    - Maps intent to agent
    - Returns: {"agent_name": "identity_agent", ...}
    ↓
[4] IdentityAgent.execute()
    - Routes to specific operation handler
    - For "get_user_details": calls GetUserDetailsTool
    - For "password_reset": calls PasswordResetTool
    ↓
[5] Tool Execution
    - GetUserDetailsTool.get_details()
      └─ MicrosoftGraphClient.get_user_details()
        └─ HTTP POST to https://graph.microsoft.com/v1.0/users/{id}
    - PasswordResetTool.reset_password()
      └─ MicrosoftGraphClient.reset_password()
        └─ HTTP POST to https://graph.microsoft.com/v1.0/users/{id}/changePassword
    ↓
[6] ResponseFormatter
    - Formats technical output to user-friendly message
    - Returns: Formatted response
    ↓
Final Response with success/error status
```

## Next Steps for Team

After understanding this flow:

1. **Amit Bhagat** - Enhance prompts.py with better prompt engineering
2. **Shreesanyog** - Integrate into LangGraph for orchestration
3. **Aman Mishra** - Add more Graph API operations
4. **Roshan** - Wire this into FastAPI endpoints

## Files Modified/Created

- ✅ `App/integration/microsoft_graph.py` - Full implementation with OAuth2
- ✅ `App/tools/identity/reset_password.py` - Complete tool implementation  
- ✅ `App/tools/identity/get_user_details.py` - New tool for user details
- ✅ `App/agents/identity_agent.py` - Updated to call tools
- ✅ `App/intent/prompts.py` - Updated with new intents
- ✅ `Scripts/demo_flow.py` - Complete demo script

## Success Criteria

✅ Ollama is running
✅ Azure AD credentials are configured
✅ Can get user details from Graph API
✅ Can reset user password
✅ Intent classification works
✅ Metadata extraction works
✅ Proper error handling
✅ Team has reference implementation

## Questions?

Check the logs in `logs/techadmin.log` for detailed execution traces.
