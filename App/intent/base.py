"""
LLM Helper Module
Author: Amit Bhagat
Purpose: Small shared helpers for creating the Ollama client and parsing its JSON output.

Two helpers, used by the classifier, the metadata extractor and the unified extractor:
  - create_llm()          : builds a ChatOllama client with consistent settings
  - parse_json_response() : safely pulls a JSON object out of the model's reply
"""

import json
import os
import re
from typing import Any, Dict, Optional

from langchain_ollama import ChatOllama
from loguru import logger

# qwen3 is a reasoning model and can wrap its answer in a <think> block.
# It may also wrap JSON in markdown fences. Both are removed before parsing.
_THINK_BLOCK = re.compile(r"<think\b[^>]*>.*?</think\s*>", re.DOTALL | re.IGNORECASE)
_LEADING_THINK = re.compile(r"^.*?</think\s*>", re.DOTALL | re.IGNORECASE)
_OPEN_THINK = re.compile(r"<think\b[^>]*>", re.IGNORECASE)
_CODE_FENCE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL | re.IGNORECASE)


def create_llm(
    model_name: Optional[str] = None,
    ollama_host: Optional[str] = None,
    temperature: float = 0.0,
) -> Optional[ChatOllama]:
    """
    Create a ChatOllama client.

    Args:
        model_name: Ollama model name (defaults to the MODEL_NAME env var)
        ollama_host: Ollama server URL (defaults to the OLLAMA_HOST env var)
        temperature: Sampling temperature; 0 keeps classification repeatable

    Returns:
        A ChatOllama instance, or None if it could not be created.
    """
    model_name = model_name or os.getenv("MODEL_NAME", "qwen3:14b")
    ollama_host = ollama_host or os.getenv("OLLAMA_HOST", "http://localhost:11434")

    try:
        # format="json" asks Ollama to constrain the output to valid JSON.
        llm = ChatOllama(
            model=model_name,
            base_url=ollama_host,
            temperature=temperature,
            format="json",
        )
        logger.info(f"Ollama client created - Model: {model_name}, Host: {ollama_host}")
        return llm
    except Exception as e:
        logger.error(f"Failed to initialize ChatOllama: {str(e)}")
        return None


def parse_json_response(response_text: str) -> Optional[Dict[str, Any]]:
    """
    Extract a JSON object from a raw LLM response.

    Handles plain JSON, JSON wrapped in a <think> block, and JSON inside markdown
    fences. Returns None instead of raising if nothing usable is found.

    Args:
        response_text: The raw text returned by the model

    Returns:
        The parsed dictionary, or None if it could not be parsed.
    """
    if not response_text:
        return None

    text = _THINK_BLOCK.sub("", response_text)
    if "</think" in text.lower():
        text = _LEADING_THINK.sub("", text)
    text = _OPEN_THINK.sub("", text).strip()

    fence = _CODE_FENCE.search(text)
    if fence:
        text = fence.group(1).strip()

    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        pass

    # Fall back to the first {...} block if the model added text around the JSON.
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        try:
            parsed = json.loads(text[start:end + 1])
            return parsed if isinstance(parsed, dict) else None
        except json.JSONDecodeError:
            pass

    logger.error(f"Could not parse JSON from LLM response: {response_text[:300]}")
    return None
