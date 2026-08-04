"""LLM client package — shared utilities for DeepSeek and Claude backends."""

import json


def extract_json(text: str) -> dict:
    """Extract JSON object from text that may contain markdown code fences.

    Shared by DeepSeekClient and ClaudeClient; both LLMs occasionally wrap
    JSON output in ```json ... ``` fences.
    """
    text = text.strip()

    # Remove markdown code fences if present
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]

    text = text.strip()
    return json.loads(text)
