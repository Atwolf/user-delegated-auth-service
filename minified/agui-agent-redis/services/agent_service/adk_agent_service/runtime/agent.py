from __future__ import annotations

from adk_agent_service.runtime.model_provider import build_model

APP_NAME = "magnum_opus_agent_service"
AGENT_NAME = "agui_adk_agent"


def build_root_agent() -> object:
    try:
        from google.adk.agents import Agent
    except ImportError as exc:
        raise RuntimeError("google-adk is required") from exc

    return Agent(
        name=AGENT_NAME,
        model=build_model(),
        instruction=(
            "Respond directly to the user. Use the AG-UI state as thread context. "
            "Redis contains run metadata only; ADK is the only agent runtime."
        ),
    )
