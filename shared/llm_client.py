"""Shared Gemini LLM client used by both Version 1 and Version 2.

The client reads the Gemini API key from the environment variable
GEMINI_API_KEY. If it is missing, it raises a clear error so the
Streamlit apps can prompt the user to supply one.
"""

import os
from typing import List, Dict, Optional

import google.generativeai as genai


class LLMClient:
    """Thin wrapper around the Google Gemini SDK."""

    def __init__(self, api_key: Optional[str] = None, model: str = "gemini-1.5-flash"):
        api_key = api_key or os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError(
                "GEMINI_API_KEY is not set. Please provide a Gemini API key "
                "(environment variable or the app's API key field)."
            )
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel(model)

    def chat(self, messages: List[Dict[str, str]], temperature: float = 0.7) -> str:
        """Send a conversation (list of role/content dicts) and return the reply."""
        # Convert OpenAI-style messages to Gemini's content format.
        gemini_history = []
        for msg in messages[:-1]:
            role = "user" if msg["role"] == "user" else "model"
            gemini_history.append({"role": role, "parts": [msg["content"]]})

        chat_session = self.model.start_chat(history=gemini_history)
        response = chat_session.send_message(
            messages[-1]["content"],
            generation_config={"temperature": temperature},
        )
        return response.text

    def generate(self, prompt: str, temperature: float = 0.7) -> str:
        """Single-turn generation."""
        response = self.model.generate_content(
            prompt, generation_config={"temperature": temperature}
        )
        return response.text
