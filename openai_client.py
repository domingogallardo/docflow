"""Helpers to initialize the OpenAI client."""
from openai import OpenAI


def build_openai_client(api_key: str | None):
    """Return an OpenAI client, or None if initialization fails."""
    try:
        return OpenAI(api_key=api_key) if api_key else OpenAI()
    except Exception:
        return None
