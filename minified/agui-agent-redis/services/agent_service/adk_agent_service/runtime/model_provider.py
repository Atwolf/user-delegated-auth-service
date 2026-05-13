from __future__ import annotations

import os


def build_model() -> object:
    if os.getenv("ANTHROPIC_API_KEY"):
        try:
            from google.adk.models.anthropic_llm import AnthropicLlm
        except ImportError as exc:
            raise RuntimeError("google-adk Anthropic support is not installed") from exc
        return AnthropicLlm(model=os.getenv("ANTHROPIC_MODEL") or "claude-sonnet-4-20250514")
    return os.getenv("GOOGLE_ADK_MODEL") or "gemini-flash-latest"
