"""DeepSeek API wrapper for structured JSON generation.

Uses the OpenAI-compatible API (https://api.deepseek.com/v1).
"""

import json
from openai import OpenAI

from . import extract_json


class DeepSeekClient:
    """Thin wrapper around the DeepSeek API for JSON-mode generation.

    Usage:
        client = DeepSeekClient(api_key="sk-...")
        result = client.generate_json(
            system_prompt="You are a helpful assistant.",
            user_prompt="Return a JSON object with keys 'a' and 'b'.",
        )
    """

    def __init__(
        self,
        api_key: str,
        model: str = "deepseek-chat",
        base_url: str = "https://api.deepseek.com",
        timeout: float = 120.0,
    ):
        self.client = OpenAI(
            api_key=api_key,
            base_url=base_url,
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
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user_prompt})

        response = self.client.chat.completions.create(
            model=self.model,
            max_tokens=max_tokens,
            temperature=0.3,
            messages=messages,
        )
        text = response.choices[0].message.content
        return extract_json(text)
