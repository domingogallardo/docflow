"""Helpers para inicializar el cliente de OpenAI."""
from openai import OpenAI


def build_openai_client(api_key: str | None):
    """Devuelve un cliente OpenAI o None si falla la inicialización."""
    try:
        return OpenAI(api_key=api_key) if api_key else OpenAI()
    except Exception:
        return None
