"""DeepSeek API wrapper for structured JSON generation.

Uses the OpenAI-compatible API (https://api.deepseek.com/v1).
"""

import json
from openai import OpenAI


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
    ):
        self.client = OpenAI(api_key=api_key, base_url=base_url)
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
        return self._extract_json(text)

    @staticmethod
    def _extract_json(text: str) -> dict:
        """Extract JSON object from text that may contain markdown fences."""
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
