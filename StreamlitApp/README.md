# StreamlitApp

Browser UI for the TechAdmin identity operations.

## Files

| File | Purpose |
|---|---|
| `app.py` | The Streamlit UI: tabs, forms, result rendering |
| `flow_service.py` | Thin layer between the UI and the existing workflow |

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

## The four tabs

**Ask** — free text, e.g. *"Get details for derhant@coforge.com"*. Runs the full
pipeline: Ollama classifies the intent and extracts the metadata, the router picks the
agent, the Identity Agent calls the tool. This is the same path as
`python Scripts/demo_flow.py`, so it shows the intent and the confidence score.

**Get user details** — a form that takes a username or email and calls Microsoft Graph
directly. No LLM call, so it responds in well under a second.

**Reset password** — the same, for password resets. The button stays disabled until a
confirmation checkbox is ticked, because a reset cannot be undone.

**History** — everything run in this browser session, downloadable as JSON.

## Why there are two ways to do the same thing

The **Ask** tab is what you demo: it shows the LLM working. The **form** tabs are what
you use when testing the Graph integration, because they take the LLM out of the loop —
if a lookup fails there, the problem is in Graph or the credentials, not in
classification.

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
