"""Claude API wrapper for structured JSON generation."""

import json
import re

from anthropic import Anthropic

from . import extract_json


class ClaudeClient:
    """Thin wrapper around the Anthropic SDK for JSON-mode generation.

    Usage:
        client = ClaudeClient(api_key="...")
        result = client.generate_json(
            system_prompt="You are a helpful assistant.",
            user_prompt="Return a JSON object with keys 'a' and 'b'.",
        )
    """

    def __init__(
        self,
        api_key: str,
        model: str = "claude-sonnet-5-20251001",
        timeout: float = 120.0,
    ):
        self.client = Anthropic(
            api_key=api_key,
            timeout=timeout,
            max_retries=1,
        )
        self.model = model

    def generate_json(
        self,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = 4096,
    ) -> dict:
        """Send a prompt and parse the response as JSON.

        Args:
            system_prompt: System-level instruction.
            user_prompt: User message content.
            max_tokens: Maximum tokens in the response.

        Returns:
            Parsed JSON dict.

        Raises:
            json.JSONDecodeError: If the response is not valid JSON.
        """
        response = self.client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        text = response.content[0].text
        return extract_json(text)
