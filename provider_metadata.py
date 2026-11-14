"""Helpful links for built-in providers, separate from the dynamic connection catalog."""

from __future__ import annotations

from typing import Any


_PROVIDERS: dict[str, dict[str, str]] = {
    "openai": {
        "provider_label": "OpenAI",
        "key_url": "https://platform.openai.com/api-keys",
        "docs_url": "https://developers.openai.com/api/docs/overview",
    },
    "anthropic": {
        "provider_label": "Anthropic",
        "key_url": "https://platform.claude.com/settings/keys",
        "docs_url": "https://docs.anthropic.com/en/api/getting-started",
    },
    "gemini": {
        "provider_label": "Google Gemini",
        "key_url": "https://aistudio.google.com/app/apikey",
        "docs_url": "https://ai.google.dev/gemini-api/docs",
    },
    "xai": {
        "provider_label": "xAI",
        "key_url": "https://console.x.ai/",
        "docs_url": "https://docs.x.ai/docs/overview",
    },
    "deepseek": {
        "provider_label": "DeepSeek",
        "key_url": "https://platform.deepseek.com/api_keys",
        "docs_url": "https://api-docs.deepseek.com/",
    },
    "ollama": {
        "provider_label": "Ollama",
        "docs_url": "https://docs.ollama.com/api/introduction",
    },
}


def provider_metadata(connection_id: str) -> dict[str, Any]:
    """Return a copy of trusted provider links for a known built-in connection."""
    return dict(_PROVIDERS.get(connection_id, {}))
