"""
Purpose:
    Terminal entry point for manually exercising the intent
    classification / metadata extraction / validation pipeline while the
    Router/Agent/API layers do not exist yet.

Scope:
    Reads one query from stdin, runs it through
    App/workflows/intent_node.py, prints the structured JSON result to
    the terminal, and writes that same result to two files:
    output/extraction_result.json and result.json (project root).

Does not handle:
    Any agent execution, routing, or the eventual FastAPI/Teams entry
    point. This is a manual developer convenience only — it is
    deliberately NOT App/main.py, which is left untouched (it currently
    contains no code) per project instructions.
"""
from __future__ import annotations

import json
from pathlib import Path

from App.workflows.intent_node import build_intent_node

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_JSON_PATH = PROJECT_ROOT / "output" / "extraction_result.json"
RESULT_JSON_PATH = PROJECT_ROOT / "result.json"


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def main() -> None:
    node = build_intent_node()

    query = input("Enter user query: ").strip()
    if not query:
        print("No query entered.")
        return

    result = node({"user_query": query})

    print("\nStructured JSON:")
    print(json.dumps(result, indent=2))

    _write_json(OUTPUT_JSON_PATH, result)
    _write_json(RESULT_JSON_PATH, result)

    print(f"\nSaved to: {OUTPUT_JSON_PATH.relative_to(PROJECT_ROOT)}")
    print(f"Saved to: {RESULT_JSON_PATH.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
