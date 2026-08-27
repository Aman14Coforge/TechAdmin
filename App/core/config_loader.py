"""
Purpose:
    Loads the project's existing YAML configuration files
    (Configs/llm_config.yaml, Configs/intent_mapping.yaml,
    Configs/app_config.yaml) for use by the new intent-classification
    module.

Scope:
    Read-only configuration loading and small derived helpers (the
    allowed-intents list, the Gemini API key).

Does not handle:
    Writing/modifying configuration, or LLM invocation itself — see
    App/core/llm_client.py.

Note on an existing inconsistency (left unmodified, per project
instructions):
    App/utils/config.py contains the line
    `from app.utils.config import load_llm_config` — i.e. it imports from
    itself (and uses a lowercase "app", while the actual folder on disk
    is "App") and never defines that function, so importing that file
    raises ImportError. This module is a separate, independent loader; it
    does not import from or modify App/utils/config.py in any way.
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import yaml

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # pragma: no cover - python-dotenv is already in requirements.txt
    pass

# Matches the existing repo's actual folder name ("Configs", capital C).
# App/models/test_ollama.py looks for "configs/llm_config.yaml" (lowercase)
# instead, which will not resolve on a case-sensitive filesystem — a
# pre-existing inconsistency in that file, left untouched per project
# instructions.
CONFIG_DIR = Path(os.getenv("TECHADMIN_CONFIG_DIR", "Configs"))


def _load_yaml(filename: str) -> dict:
    path = CONFIG_DIR / filename
    with open(path, "r", encoding="utf-8") as file:
        return yaml.safe_load(file) or {}


@lru_cache
def load_llm_config() -> dict:
    """Returns the parsed, UNCHANGED contents of the existing
    Configs/llm_config.yaml (provider, model_name, temperature, top_p,
    timeout)."""
    return _load_yaml("llm_config.yaml")


@lru_cache
def load_intent_mapping() -> dict:
    """Returns the parsed, UNCHANGED contents of the existing
    Configs/intent_mapping.yaml (intent -> owning agent)."""
    return _load_yaml("intent_mapping.yaml")


@lru_cache
def load_app_config() -> dict:
    """Returns the parsed, UNCHANGED contents of the existing
    Configs/app_config.yaml."""
    return _load_yaml("app_config.yaml")


def get_allowed_intents() -> list[str]:
    """Derives the controlled set of classifiable intents directly from
    Configs/intent_mapping.yaml's top-level keys, plus "unknown" for
    anything that doesn't match — so the classifier stays in sync with
    that existing config file without duplicating or modifying it."""
    mapping = load_intent_mapping()
    return list(mapping.keys()) + ["unknown"]


def get_gemini_api_key() -> str | None:
    """The Gemini fallback API key — sourced only from the environment,
    never from YAML and never hardcoded."""
    return os.getenv("GEMINI_API_KEY")
