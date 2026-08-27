# Local Setup — Intent Classification + Metadata Extraction Module

This covers only what's needed to run the intent-classification module
added around the existing TechAdmin project. It does not touch or
document anything about the existing files.

## 1. Install Ollama

Download and install Ollama for your OS from https://ollama.com/download.

## 2. Verify Ollama

```bash
ollama --version
```

## 3. Pull the configured model

The model is already fixed in the existing `Configs/llm_config.yaml`
(`qwen3:14b`) — pull that exact model:

```bash
ollama pull qwen3:14b
```

> Note: some local testing referenced `qwen3:4b`. `Configs/llm_config.yaml`
> is left unmodified per project instructions, so the model actually used
> is whatever it specifies (`qwen3:14b`) unless you change that file
> yourself. The response-parsing behavior described in
> `INTENT_MODULE_README.md` is robust to either model's output style.

## 4. Verify the model is available

```bash
ollama list
```

You should see `qwen3:14b` in the output.

## 5. Start Ollama

If it isn't already running as a background service:

```bash
ollama serve
```

The application expects Ollama to be reachable at the default local
address:

```
http://localhost:11434
```

## 6. Test Qwen independently (optional, but useful)

```bash
ollama run qwen3:14b
```

This opens a direct chat with the model — if it responds, the model is
correctly installed and available locally, independent of anything in
this codebase.

## 7. Python environment

```bash
python -m venv venv
```

Activate it:

```bash
# Windows
venv\Scripts\activate

# macOS / Linux
source venv/bin/activate
```

Install the existing project's dependencies (unchanged):

```bash
pip install -r requirements.txt
```

Then install the one additional dependency this module needs for the
Gemini fallback path (kept in a separate file — the existing
`requirements.txt` was not modified):

```bash
pip install -r requirements-additional.txt
```

## 8. Gemini fallback configuration

Copy the provided template and fill in your key:

```bash
cp .env.example .env
```

```
GEMINI_API_KEY=<your-key-here>
```

Never commit a real key. If `GEMINI_API_KEY` is left unset, the module
still works fully on the normal path (Ollama succeeding) — it simply has
no fallback available if Ollama fails, and will report that clearly
instead of producing a result.

## Running it

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

## Running the tests

No live Ollama instance or Gemini key is required for the automated test
suite — see `INTENT_MODULE_README.md` for details on the fake LLM client
the tests use instead.

```bash
pytest -q
```
