# App/intent

Intent classification and metadata extraction for the TechAdmin workflow.
Author: Amit Bhagat

## Files

| File | What it does |
|---|---|
| `unified_extractor.py` | Identifies the intent **and** extracts the metadata in a single Ollama call. This is what the workflow uses. |
| `classifier.py` | Identifies the intent only. Used when metadata is not needed, or when testing classification on its own. |
| `metadata_extractor.py` | Extracts metadata only, for a request whose intent is already known. |
| `prompts.py` | The three prompt templates, plus the shared intent and extraction rules they are built from. |
| `schemas.py` | Pydantic models that validate whatever the LLM returns, and the per-intent required-field rules. |
| `base.py` | Two shared helpers: create the Ollama client, and parse JSON out of the model's reply. |

## Flow

```
user request
     |
     v
UnifiedIntentMetadataExtractor.extract_all()
     |
     |-- UNIFIED_EXTRACTION_PROMPT  (prompts.py)
     |-- create_llm() / parse_json_response()  (base.py)
     |-- ExtractionResult validation  (schemas.py)
     v
{ intent, confidence, explanation, metadata, success }
     |
     v
validate_metadata()  ->  AgentRouter  ->  IdentityAgent
```

## Supported intents

`password_reset`, `account_unlock`, `grant_access`, `revoke_access`, `get_user_details`,
plus `unknown` for requests that are outside the scope of identity operations.

## What Pydantic gives us

The LLM returns free-form JSON, so the models in `schemas.py` sit between the model and
the rest of the app:

- **`SupportedIntent`** – the intent is always one of the known values. An unrecognised
  intent becomes `unknown` instead of reaching `AgentRouter.route()`, which raises
  `ValueError` on a key it does not have.
- **`UserMetadata`** – `"null"`, `"N/A"` and `""` are turned into a real `None`. Those
  strings are truthy in Python, so without this a request could pass validation and then
  be sent to Microsoft Graph as `username="null"`. All four keys are always present.
- **`IntentResult.confidence`** – always a float between 0 and 1, even if the model
  returns `"0.95"` as a string or `95` as a percentage. `demo_flow.py` compares this
  value with `< 0.7`, which needs a number.
- **`ExtractionResult.metadata`** – never `None`, so `metadata.get(...)` downstream is
  always safe.
- **`validate_metadata()`** – required fields are declared as data in
  `INTENT_REQUIRED_FIELDS`, covering all five intents in one place.

## JSON parsing

`qwen3:14b` is a reasoning model and can wrap its answer in a `<think> ... </think>`
block, which makes a plain `json.loads()` fail. `parse_json_response()` in `base.py`
strips `<think>` blocks and markdown fences before parsing, and falls back to the first
`{...}` block if the model adds text around the JSON. `create_llm()` also passes
`format="json"` so Ollama constrains the output to valid JSON in the first place.

## Usage

```python
from App.intent.unified_extractor import UnifiedIntentMetadataExtractor

extractor = UnifiedIntentMetadataExtractor()
result = extractor.extract_all("Please reset the password for john.doe")

# result["intent"]                -> "password_reset"
# result["metadata"]["username"]  -> "john.doe"
# result["success"]               -> True

is_valid, message = extractor.validate_metadata(result["metadata"], result["intent"])
```

## Configuration

Read from environment variables, as before:

- `MODEL_NAME` (default `qwen3:14b`)
- `OLLAMA_HOST` (default `http://localhost:11434`)
