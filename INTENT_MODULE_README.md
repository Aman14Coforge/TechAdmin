# Intent Classification + Metadata Extraction Module

New functionality built **around** the existing TechAdmin project. No
existing file was modified, renamed, moved, or deleted — see the
verification section at the bottom.

**Scope note:** this delivery is scoped back to the first milestone —
Intent Classification + Metadata Extraction + Validation + LangGraph
Intent Node — with state now represented as a Pydantic model instead of
a `TypedDict`. A later pass added an Identity Agent tool-dispatch layer
on top of this; that has been left out of this delivery per instruction
to rebuild "only till the 1st step."

## Scope

Implements exactly: Intent Design, Prompt Engineering, Metadata
Extraction, Input Validation, LangGraph Intent Node — stopping at
structured, validated JSON. Does **not** implement the Router, Identity
Agent, Password Reset Tool/API, authentication, Network/Patch agents, or
any end-to-end workflow.

## Why Pydantic instead of TypedDict for state

`App/workflows/state.py`'s `IntentState` is a Pydantic `BaseModel`, not a
`TypedDict` — the only place in the codebase that used `TypedDict` (a
grep for it now returns nothing). This matches how every other
structured value in this project is already represented
(`App/schemas/extraction.py`'s `ExtractedFields`), for the same reasons:

- **Runtime validation.** A `TypedDict` is a type-checker-only construct
  — nothing stops `IntentState(is_valid="oops")` at runtime. A Pydantic
  model raises `ValidationError` immediately if a field gets the wrong
  type.
- **Real defaults, not just type hints.** `missing_fields: list[str] =
  Field(default_factory=list)` guarantees every instance gets its own
  list — a plain `TypedDict` has no defaults at all; a naive mutable
  default (`= []`) would be shared across instances, a classic bug (see
  `tests/test_state.py::test_intent_state_missing_fields_defaults_are_independent_instances`).
- **LangGraph supports it natively.** `StateGraph(IntentState)` works
  exactly the same whether `IntentState` is a `TypedDict` or a Pydantic
  model — confirmed directly against the LangGraph version this project
  uses (`tests/test_state.py::test_intent_state_works_as_a_langgraph_state_schema`).
  Nodes registered into a compiled graph receive a validated `IntentState`
  instance; called directly (as every test and `scripts/run_intent_cli.py`
  do), the node also accepts a plain dict and normalizes it internally.

```python
class IntentState(BaseModel):
    user_query: str = ""
    intent: str | None = None
    username: str | None = None
    email: str | None = None
    employee_id: str | None = None
    missing_fields: list[str] = Field(default_factory=list)
    is_valid: bool = False
    error: str | None = None
```

`App/workflows/intent_node.py`'s node function normalizes whatever it's
given (`dict` or `IntentState`) via `IntentState.model_validate(state)`
at the top, then uses plain attribute access (`validated_state.user_query`)
instead of `state.get("user_query")` throughout. It still **returns a
plain dict** of the full result — that part of the contract didn't
change, so `scripts/run_intent_cli.py` and every existing test that does
`json.dumps(result)` needed no changes at all.

## How it works

```
user_query
    │
    ▼
App/intent/metadata_extractor.extract_raw()   — ONE logical LLM call
    │                                            (with an internal
    │                                            retry-then-fallback
    │                                            policy — see below)
    ▼
raw {"intent", "username", "email", "employee_id"}   — already parsed;
    │                                                   see the response-
    │                                                   parsing stage below
    ├──▶ App/intent/classifier.classify_intent()   — resolves against
    │                                                 Configs/intent_mapping.yaml,
    │                                                 degrades to "unknown"
    │                                                 if not recognized
    │
    └──▶ App/schemas/extraction.ExtractedFields    — normalizes blank/
                                                       malformed values to None
    │
    ▼
App/intent/validator.validate_fields()   — deterministic, no LLM involved
    │
    ▼
App/workflows/intent_node.build_intent_node()   — combines all of the
    │                                              above into one LangGraph
    │                                              node function, using
    │                                              IntentState (Pydantic)
    ▼
Structured JSON result
```

Classification and extraction happen in a **single** LLM call (not two
separate ones) — both come from the same piece of text, and splitting
them would only double LLM cost without adding accuracy. The prompt
(`App/intent/prompts.py`) builds its allowed-intent list dynamically from
the existing `Configs/intent_mapping.yaml`, so it can never drift out of
sync with that file.

### Response parsing — the raw model text is never trusted directly

Local Qwen models frequently wrap their JSON answer in reasoning,
explanation, or markdown even when explicitly asked for JSON-only output.
`App/core/response_parser.py` is a dedicated pipeline stage that sits
between "raw model text" and "parsed dict":

```
Raw LLM Response
    ↓
1. Whole response already valid JSON?  → use it
    ↓ no
2. A ```json fenced block that parses? → use it
    ↓ no
3. Balanced-brace scan of the entire text (string-literal aware, so a
   `{` inside a quoted sentence never confuses it) → try every `{...}`
   substring found, preferring one with an "intent" key
    ↓ none parse
Raise ResponseParsingError (never guesses, never returns partial data)
```

The raw text is logged at `DEBUG` level only, and only when extraction
actually fails — never returned, never surfaced anywhere in the final
JSON.

### Ollama → Gemini fallback (parse-aware)

`App/core/llm_client.py`'s `OllamaWithGeminiFallback.complete_json`:

```
Ollama raw call
    │
    ├── connection/timeout failure ──▶ Gemini fallback directly
    │                                   (retrying an unreachable server
    │                                    doesn't help)
    │
    └── succeeds ──▶ App/core/response_parser.extract_json_object()
            │
            ├── parses ──▶ return result (Gemini never touched)
            │
            └── fails to parse ──▶ ONE retry against Ollama with a
                    │                corrective prompt appended
                    │
                    ├── retry parses ──▶ return result
                    │
                    └── retry also fails/errors ──▶ Gemini fallback
                            │
                            ├── not configured (no GEMINI_API_KEY)
                            │       ──▶ raise LLMInvocationError
                            │
                            ├── succeeds ──▶ return result
                            │
                            └── also fails ──▶ raise LLMInvocationError
```

A parse failure is treated the same as a connection failure for fallback
purposes. Gemini is never called speculatively alongside Ollama, and
never called when Ollama's response (first or retried) already parses.

### Validation is deterministic, not LLM-trusted

`App/intent/validator.py` defines `MANDATORY_FIELDS_BY_INTENT` in exactly
one place (`password_reset` → `["username", "email", "employee_id"]`) and
computes `missing_fields`/`is_valid` purely from what `ExtractedFields`
actually contains — the LLM's own opinion is never consulted.

## New files

```
TechAdmin-main/
│
├── App/
│   ├── main.py                     EXISTING — UNCHANGED (still empty)
│   ├── __init__.py                 NEW (namespace marker; none existed)
│   │
│   ├── core/                       NEW
│   │   ├── __init__.py             NEW
│   │   ├── config_loader.py        NEW — reads the existing Configs/*.yaml
│   │   ├── llm_client.py           NEW — Ollama primary, Gemini fallback
│   │   └── response_parser.py      NEW — robust JSON extraction from
│   │                                      noisy raw LLM text
│   │
│   ├── intent/                     NEW
│   │   ├── __init__.py             NEW
│   │   ├── prompts.py              NEW
│   │   ├── metadata_extractor.py   NEW
│   │   ├── classifier.py           NEW
│   │   └── validator.py            NEW
│   │
│   ├── workflows/                  NEW
│   │   ├── __init__.py             NEW
│   │   ├── state.py                NEW — IntentState (Pydantic BaseModel)
│   │   └── intent_node.py          NEW
│   │
│   ├── schemas/                    NEW
│   │   ├── __init__.py             NEW
│   │   └── extraction.py           NEW — ExtractedFields (Pydantic BaseModel)
│   │
│   ├── models/
│   │   └── test_ollama.py          EXISTING — UNCHANGED
│   │
│   └── utils/
│       └── config.py               EXISTING — UNCHANGED (see note below)
│
├── output/                         NEW
│   └── .gitkeep                    NEW
│
├── scripts/                        NEW
│   ├── __init__.py                 NEW
│   └── run_intent_cli.py           NEW — terminal entry point
│
├── tests/                          NEW
│   ├── __init__.py                 NEW
│   ├── conftest.py                 NEW
│   ├── test_classifier.py          NEW
│   ├── test_metadata_extractor.py  NEW
│   ├── test_validator.py           NEW
│   ├── test_response_parser.py     NEW — robust JSON extraction cases
│   ├── test_llm_client.py          NEW
│   ├── test_state.py               NEW — IntentState Pydantic behavior
│   └── test_intent_node.py         NEW
│
├── docs/                           NEW
│   └── OLLAMA_SETUP.md             NEW
│
├── Configs/
│   ├── app_config.yaml             EXISTING — UNCHANGED
│   ├── intent_mapping.yaml         EXISTING — UNCHANGED
│   └── llm_config.yaml             EXISTING — UNCHANGED
│
├── .gitignore                      EXISTING — UNCHANGED
├── README.md                       EXISTING — UNCHANGED
├── cammands                        EXISTING — UNCHANGED
├── requirements.txt                EXISTING — UNCHANGED
│
├── requirements-additional.txt     NEW — the one extra package (Gemini)
├── pyproject.toml                  NEW — pytest config only
├── .env.example                    NEW — GEMINI_API_KEY template
└── INTENT_MODULE_README.md         NEW — this file
```

## Existing-file inconsistencies found (left untouched, per instructions)

Two pre-existing issues in `App/utils/config.py`, neither modified — the
new code is entirely independent of this file:

1. It contains `from app.utils.config import load_llm_config` — importing
   from **itself** — and never actually defines `load_llm_config`
   anywhere in the file. Importing this module raises `ImportError`
   (or a circular-import error) as written.
2. That import also uses a lowercase `app`, while the real folder on disk
   is `App` (capital A) — this only "works" on a case-insensitive
   filesystem (Windows) and would fail on Linux/Mac even if the
   self-import problem above were fixed.

Separately, `App/models/test_ollama.py` reads
`Path("configs/llm_config.yaml")` (lowercase `configs`), while the real
folder is `Configs` (capital C) — same case-sensitivity caveat, also left
untouched.

`App/core/config_loader.py` (new) avoids both problems: it points at
`Configs/` (matching the real folder) and does not import from
`App/utils/config.py` at all.

## The one additional dependency

The existing `requirements.txt` already covers the Ollama path
(`langchain-ollama` is already listed) and was **not modified**. Gemini
fallback needs one more package, kept in a separate file:

```bash
pip install -r requirements.txt              # existing, unchanged
pip install -r requirements-additional.txt    # new — just langchain-google-genai
```

## Running it

Full setup steps (Ollama install → model pull → verification → venv →
dependencies → environment variables) are in `docs/OLLAMA_SETUP.md`.

```bash
python -m scripts.run_intent_cli
```

```
Enter user query: Reset password for aman.gupta. My email is aman.gupta@company.com and employee id is EMP12345.

Structured JSON:
{
  "error": null,
  "intent": "password_reset",
  "username": "aman.gupta",
  "email": "aman.gupta@company.com",
  "employee_id": "EMP12345",
  "missing_fields": [],
  "is_valid": true
}

Saved to: output/extraction_result.json
Saved to: result.json
```

Both files get the same content — `output/extraction_result.json` matches
the location this task's own suggested structure named, and `result.json`
at the project root matches what was explicitly requested directly in
chat. Each run **overwrites** both with the latest single result (one JSON
object, not an accumulating log).

### Missing-info example

```
Enter user query: Reset password for aman.gupta

Structured JSON:
{
  "error": null,
  "intent": "password_reset",
  "username": "aman.gupta",
  "email": null,
  "employee_id": null,
  "missing_fields": ["email", "employee_id"],
  "is_valid": false
}
```

### Fallback example (Ollama unavailable)

```json
{
  "error": "Ollama failed and no Gemini fallback is configured (set GEMINI_API_KEY to enable it): Ollama request failed: [Errno 111] Connection refused",
  "intent": null,
  "username": null,
  "email": null,
  "employee_id": null,
  "missing_fields": [],
  "is_valid": false
}
```

## Tests

```bash
pytest -q
```

62 tests, none requiring a live Ollama instance or a real Gemini key:

- `tests/test_classifier.py` — intent resolution / degradation to unknown
- `tests/test_metadata_extractor.py` — username/email/employee_id
  extraction, combined and individually, empty-query handling
- `tests/test_validator.py` — every missing-field combination,
  deterministic validation, malformed-email handling
- `tests/test_response_parser.py` — pure JSON, markdown-fenced JSON, JSON
  surrounded by reasoning text, braces inside string values, minor
  formatting noise, and malformed/empty/array-only input that must raise
  rather than guess
- `tests/test_llm_client.py` — Ollama success, the noisy-reasoning
  scenario end to end through the real `OllamaLLMClient`,
  parse-failure-triggers-one-retry, retry-still-fails-triggers-Gemini,
  connection-failure-skips-straight-to-Gemini, both-failing — with
  `langchain_ollama.ChatOllama` / `langchain_google_genai.ChatGoogleGenerativeAI`
  monkeypatched so no network call ever happens
- `tests/test_state.py` — `IntentState` is a real Pydantic model: type
  validation, defaults (including the mutable-default-list trap), and
  that it works directly as a `StateGraph` schema
- `tests/test_intent_node.py` — full pipeline end to end, a check that
  the node function drops into a real `langgraph.graph.StateGraph`
  correctly, that it accepts an `IntentState` instance directly (not just
  a dict), and `test_node_output_contains_only_clean_json_never_raw_reasoning`
  — proving reasoning-wrapped Qwen output never leaks into the result

`tests/conftest.py`'s `FakeLLMClient` is a regex-based stand-in
implementing the same `complete_json(system_prompt, user_prompt) -> dict`
contract the real Ollama/Gemini clients use — it does not test either
provider's actual language understanding, only this module's own logic
around them.

## Scope verification

This implementation stops at **Intent Classification + Metadata
Extraction + Validation + LangGraph Intent Node**. It explicitly does
**not** implement:

- Identity Agent
- Router
- Password Reset Tool
- Password Reset API / API client / authentication
- Network Agent, Patch Agent
- Full end-to-end workflow or agent orchestration beyond this one node

`App/workflows/intent_node.build_intent_node()` returns a function that
accepts either a dict or an `IntentState` instance and returns a plain
`dict` result — the exact seam where a future developer registers it
into a larger `StateGraph` alongside a Router and downstream agents,
without needing to change anything in this module.
