# StreamlitApp

Browser UI for the TechAdmin identity operations.

## Files

| File | Purpose |
|---|---|
| `app.py` | The Streamlit UI: sign-in, sidebar, assistant chat, result cards, history, directory |
| `ui_theme.py` | All CSS (Coforge navy/orange theme) and inline SVG icons |
| `flow_service.py` | Thin layer between the UI and the LangGraph workflow (unchanged) |
| `investigation_report_ui.py` | Failed sign-in / lockout report renderer |
| `preview_backend.py` | Sample-data backend for `TECHADMIN_UI_PREVIEW=true` (no Ollama, Graph or DB) |

Theme colours and fonts are also set in `.streamlit/config.toml` (`[theme]`, `[theme.sidebar]`).

## Where these go

```
TechAdmin/
├── App/
├── Configs/
├── Scripts/
│   └── demo_flow.py
├── StreamlitApp/          <-- new folder
│   ├── app.py
│   ├── flow_service.py
│   └── README.md
├── .env
└── requirements.txt
```

Nothing else in the project changes, apart from `streamlit` being added to
`requirements.txt`.

Microsoft Entra SSO is enabled through `.streamlit/secrets.toml`. The optional
local test-account login is disabled by default. For local-only testing, set
`TECHADMIN_LOCAL_LOGIN_ENABLED=true`, `TECHADMIN_LOCAL_LOGIN_USERNAME`, and
`TECHADMIN_LOCAL_LOGIN_PASSWORD` in the process environment. Never commit the
password or enable this fallback in a shared or production deployment.

## Running

From the **project root**, not from inside `StreamlitApp/`:

```bash
# 1. install (once)
pip install -r requirements.txt

# 2. make sure Ollama is running and the model is pulled
ollama serve
ollama pull qwen3:14b

# 3. start the UI
streamlit run StreamlitApp/app.py
```

It opens at `http://localhost:8501`. Use a different port with
`streamlit run StreamlitApp/app.py --server.port 8502`.

## Required .env

The same file `Scripts/demo_flow.py` already uses:

```
OLLAMA_HOST=http://localhost:11434
MODEL_NAME=qwen3:14b

GRAPH_CLIENT_ID=your-client-id
GRAPH_CLIENT_SECRET=your-client-secret
GRAPH_TENANT_ID=your-tenant-id
```

The sidebar shows which of these were found, without printing the secret values.

## UI preview mode

To work on the interface without Ollama, Microsoft Graph, PowerShell or PostgreSQL:

```bash
# macOS / Linux
TECHADMIN_UI_PREVIEW=true streamlit run StreamlitApp/app.py
# Windows PowerShell
$env:TECHADMIN_UI_PREVIEW="true"; streamlit run StreamlitApp/app.py
```

Preview mode uses in-memory sample users (amit.bhagat@, migrationtest2@, migrationtest3@coforge.com),
accepts any test-account sign-in and shows a "Preview · sample data" badge. **Never enable it on a
shared or production deployment.**

## Screens

**Sign-in** — split screen; Microsoft SSO and Test account tabs. Same rules as before: the test
account works only when `TECHADMIN_LOCAL_LOGIN_ENABLED=true`, and every identity is checked against
`app_users`.

**Assistant** — chat with the LangGraph pipeline. Results render as cards:
directory record (status tiles, Overview / Group memberships tabs, copy details), approval
(Approve and run / Cancel, or reply "yes" / "no"), password reset (masked password, send to
manager, download TXT), investigation report, and error/policy-blocked cards. Suggestion chips
under the latest result offer the next likely action. "Technical details" under each message shows
intent, confidence, IDs and the redacted raw response.

**Request history** — your requests from the operation audit log (`get_user_request_history`).

**Directory** — a read-only lookup form that runs "Get user details for …" through the same pipeline.

The **?** icon in the top bar holds example queries, system status and the Ollama connection test.

## Design notes

`flow_service.py` imports `DemoFlow` from `Scripts/demo_flow.py` rather than copying its
logic, so the UI and the terminal demo can never drift apart. `Scripts/` is not a Python
package, which is why `flow_service.py` adds it to `sys.path` before importing.

`get_service()` is wrapped in `@st.cache_resource`. Streamlit re-runs the whole script on
every interaction, so without it the Ollama and Graph clients would be rebuilt on every
click and the cached Graph access token thrown away each time.

## Troubleshooting

| Symptom | Cause |
|---|---|
| `ModuleNotFoundError: No module named 'App'` | Started from inside `StreamlitApp/`. Run from the project root. |
| Sidebar shows Graph credentials missing | `.env` is absent or in the wrong folder. It must be at the project root. |
| "Cannot reach Ollama" | `ollama serve` is not running, or `OLLAMA_HOST` is wrong. |
| Ask tab is slow, forms are fast | Expected. The Ask tab makes an LLM call first. |
| "User not found in Azure AD" | The flow worked; Graph did not find that user. Check the identifier. |

Detailed logs go to `logs/techadmin.log`, the same as the terminal demo.
