from __future__ import annotations

import json
import logging
import os
import re
from collections.abc import Iterable
from dataclasses import dataclass
from importlib import import_module
from inspect import isawaitable
from typing import Any, Protocol, cast, runtime_checkable
from uuid import uuid4

from workflow_core import TOOL_AUTHORIZATION_CATALOG, ToolIntent, get_tool_authorization

from .models import SanitizedWorkflowContext

DEFAULT_ANTHROPIC_MODEL = "claude-haiku-4-5-20251001"
ADK_APP_NAME = "magnum_opus_agent_service"
_ADK_RUN_ATTEMPTS = 2
_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class AdkRuntimeTypes:
    agent_type: type[Any]
    content_type: type[Any]
    part_type: type[Any]
    runner_type: type[Any]
    session_service_type: type[Any]
    anthropic_llm_type: type[Any] | None = None


class ToolIntentProvider(Protocol):
    async def propose(
        self,
        context: SanitizedWorkflowContext,
        *,
        allowed_tool_names: set[str] | None,
        available_tool_names: set[str],
    ) -> list[ToolIntent]: ...


@dataclass(frozen=True)
class AgentRuntimeResult:
    assistant_message: str
    tool_intents: list[ToolIntent]


@runtime_checkable
class AgentRuntimeProvider(ToolIntentProvider, Protocol):
    async def run(
        self,
        context: SanitizedWorkflowContext,
        *,
        allowed_tool_names: set[str] | None,
        available_tool_names: set[str],
    ) -> AgentRuntimeResult: ...


class GoogleAdkToolIntentProvider:
    """Google ADK adapter for the Agent Service coordinator/dispatcher runtime."""

    def __init__(
        self,
        *,
        enabled: bool | None = None,
        model: str | None = None,
    ) -> None:
        self._enabled = (
            enabled
            if enabled is not None
            else os.getenv("AGENT_SERVICE_ADK_ENABLED", "true").casefold()
            not in {"0", "false", "no", "off"}
        )
        self._model: str = (
            model
            or os.getenv("GOOGLE_ADK_MODEL")
            or os.getenv("ANTHROPIC_MODEL")
            or DEFAULT_ANTHROPIC_MODEL
        )
        self._agent: object | None = None
        self._runner: object | None = None
        self._runtime_types: AdkRuntimeTypes | None = None
        self._session_service: object | None = None
        self._adk_unavailable = False

    async def propose(
        self,
        context: SanitizedWorkflowContext,
        *,
        allowed_tool_names: set[str] | None,
        available_tool_names: set[str],
    ) -> list[ToolIntent]:
        return (
            await self.run(
                context,
                allowed_tool_names=allowed_tool_names,
                available_tool_names=available_tool_names,
            )
        ).tool_intents

    async def run(
        self,
        context: SanitizedWorkflowContext,
        *,
        allowed_tool_names: set[str] | None,
        available_tool_names: set[str],
    ) -> AgentRuntimeResult:
        if not self._enabled:
            raise RuntimeError("Google ADK agent runtime is disabled")
        if not self._ensure_agent():
            raise RuntimeError("Google ADK agent runtime is unavailable")
        return await self._run_agent(
            context,
            allowed_tool_names=allowed_tool_names,
            available_tool_names=available_tool_names,
        )

    def _ensure_agent(self) -> bool:
        if self._agent is not None:
            return True
        if self._adk_unavailable:
            return False

        adk_types = _load_adk_types()
        if adk_types is None:
            self._adk_unavailable = True
            return False

        try:
            self._agent = adk_types.agent_type(
                name="magnum_opus_coordinator",
                model=self._adk_model(adk_types),
                instruction=(
                    "Coordinate workflow planning from sanitized user/session context only. "
                    "The user message contains the authoritative tool_contracts array; "
                    "do not call tools or functions. "
                    "Return only JSON with assistant_message and a top-level tool_intents "
                    "array. assistant_message is concise user-visible narration. Each "
                    "tool intent may include tool_name, arguments, reason, agent_name, "
                    "and mcp_server. Choose only tools that directly satisfy the user "
                    "request. If the user asks to inspect, restart, update, rotate, "
                    "or otherwise operate on a resource and a matching allowed tool "
                    "exists, you must emit that tool intent. Leave tool_intents empty "
                    "only when no allowed tool contract matches the user request. "
                    "Server-side workflow_core dispatch remains authoritative for "
                    "authorization, HITL, and execution."
                ),
                tools=[],
            )
            self._session_service = adk_types.session_service_type()
            self._runner = adk_types.runner_type(
                agent=self._agent,
                app_name=ADK_APP_NAME,
                session_service=self._session_service,
            )
            self._runtime_types = adk_types
        except Exception:
            self._adk_unavailable = True
            return False
        return True

    def _adk_model(self, adk_types: AdkRuntimeTypes) -> object:
        if self._model.startswith("claude-") and adk_types.anthropic_llm_type is not None:
            return adk_types.anthropic_llm_type(model=self._model)
        return self._model

    async def _run_agent(
        self,
        context: SanitizedWorkflowContext,
        *,
        allowed_tool_names: set[str] | None,
        available_tool_names: set[str],
    ) -> AgentRuntimeResult:
        if self._runner is None or self._runtime_types is None or self._session_service is None:
            raise RuntimeError("Google ADK runner is not initialized")

        last_error: Exception | None = None
        for attempt in range(1, _ADK_RUN_ATTEMPTS + 1):
            try:
                text = await self._run_agent_text(
                    context,
                    allowed_tool_names=allowed_tool_names,
                    available_tool_names=available_tool_names,
                )
                if not text:
                    raise RuntimeError("Google ADK agent runtime returned no output")
                return _parse_agent_runtime_result(
                    text,
                    available_tool_names=available_tool_names,
                    default_agent_name="google_adk_coordinator",
                    default_reason="Google ADK coordinator output.",
                    metadata_prefix="google_adk",
                )
            except Exception as exc:
                last_error = exc
                _log_adk_run_failure(exc, attempt=attempt, attempts=_ADK_RUN_ATTEMPTS)

        if (
            isinstance(last_error, RuntimeError)
            and str(last_error) == "Google ADK agent runtime returned no output"
        ):
            raise last_error
        raise RuntimeError("Google ADK agent runtime failed") from last_error

    async def _run_agent_text(
        self,
        context: SanitizedWorkflowContext,
        *,
        allowed_tool_names: set[str] | None,
        available_tool_names: set[str],
    ) -> str:
        if self._runner is None or self._runtime_types is None or self._session_service is None:
            raise RuntimeError("Google ADK runner is not initialized")

        runner = cast(Any, self._runner)
        runtime_types = self._runtime_types
        session_service = cast(Any, self._session_service)
        session_id = f"adk-{uuid4().hex}"
        created_session = session_service.create_session(
            app_name=ADK_APP_NAME,
            user_id=context.user_id,
            session_id=session_id,
            state={
                "allowed_tools": sorted(allowed_tool_names)
                if allowed_tool_names is not None
                else None,
                "available_tools": sorted(available_tool_names),
                "session_id": context.session_id,
                "tenant_id": context.tenant_id,
                "token_ref": context.token_ref,
            },
        )
        if isawaitable(created_session):
            await created_session

        message = runtime_types.content_type(
            role="user",
            parts=[
                runtime_types.part_type.from_text(
                    text=_adk_user_prompt(
                        context,
                        allowed_tool_names=allowed_tool_names,
                        available_tool_names=available_tool_names,
                    )
                )
            ],
        )
        final_chunks: list[str] = []
        observed_chunks: list[str] = []
        async for event in runner.run_async(
            user_id=context.user_id,
            session_id=session_id,
            new_message=message,
        ):
            chunk = _extract_adk_event_text(event)
            if not chunk:
                continue
            if _is_adk_final_response(event):
                final_chunks.append(chunk)
            else:
                observed_chunks.append(chunk)
        return "\n".join(final_chunks or observed_chunks).strip()


def _parse_agent_runtime_result(
    text: str,
    *,
    available_tool_names: set[str],
    default_agent_name: str,
    default_reason: str,
    metadata_prefix: str,
) -> AgentRuntimeResult:
    decoded = _loads_json_fragment(text)
    assistant_message = ""
    if isinstance(decoded, dict):
        decoded_payload = cast(dict[str, Any], decoded)
        message = decoded_payload.get("assistant_message")
        if isinstance(message, str):
            assistant_message = message.strip()
    return AgentRuntimeResult(
        assistant_message=assistant_message,
        tool_intents=_parse_tool_intents_from_text(
            text,
            available_tool_names=available_tool_names,
            default_agent_name=default_agent_name,
            default_reason=default_reason,
            metadata_prefix=metadata_prefix,
        ),
    )


def _parse_tool_intents_from_text(
    text: str,
    *,
    available_tool_names: set[str],
    default_agent_name: str,
    default_reason: str,
    metadata_prefix: str,
) -> list[ToolIntent]:
    decoded = _loads_json_fragment(text)
    if isinstance(decoded, dict):
        decoded_payload = cast(dict[str, Any], decoded)
        raw_intents = decoded_payload.get("tool_intents", [])
    else:
        raw_intents = decoded
    if not isinstance(raw_intents, list):
        return []

    intents: list[ToolIntent] = []
    for raw_intent in cast(list[object], raw_intents):
        if isinstance(raw_intent, dict):
            intent = _tool_intent_from_payload(
                cast(dict[str, Any], raw_intent),
                available_tool_names=available_tool_names,
                default_agent_name=default_agent_name,
                default_reason=default_reason,
                metadata_prefix=metadata_prefix,
            )
            if intent is not None:
                intents.append(intent)
    return intents


def _loads_json_fragment(text: str) -> object:
    stripped = text.strip()
    if not stripped:
        return {}
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        start = min(_positions(stripped, ("{", "[")), default=-1)
        end = max(_positions(stripped, ("}", "]")), default=-1)
        if start < 0 or end < start:
            return {}
        return json.loads(stripped[start : end + 1])


def _log_adk_run_failure(exc: Exception, *, attempt: int, attempts: int) -> None:
    _LOGGER.warning(
        "Google ADK agent runtime attempt %s/%s failed: %s",
        attempt,
        attempts,
        _safe_exception_summary(exc),
    )


def _safe_exception_summary(exc: Exception) -> str:
    message = str(exc)
    for secret in _configured_secret_values():
        message = message.replace(secret, "[redacted]")
    return f"{exc.__class__.__name__}: {message}" if message else exc.__class__.__name__


def _configured_secret_values() -> list[str]:
    names = (
        "ANTHROPIC_API_KEY",
        "GOOGLE_API_KEY",
        "GOOGLE_GENAI_API_KEY",
        "GOOGLE_APPLICATION_CREDENTIALS",
    )
    return [
        value
        for name in names
        if (value := os.getenv(name)) is not None and len(value) >= 8
    ]


def _positions(value: str, needles: Iterable[str]) -> list[int]:
    positions: list[int] = []
    for needle in needles:
        position = value.find(needle)
        if position >= 0:
            positions.append(position)
        reverse_position = value.rfind(needle)
        if reverse_position >= 0:
            positions.append(reverse_position)
    return positions


def _tool_intent_from_payload(
    payload: dict[str, Any],
    *,
    available_tool_names: set[str],
    default_agent_name: str,
    default_reason: str,
    metadata_prefix: str,
) -> ToolIntent | None:
    tool_name = payload.get("tool_name")
    if not isinstance(tool_name, str) or not tool_name:
        return None
    if tool_name not in available_tool_names:
        return None
    arguments = payload.get("arguments", {})
    if not isinstance(arguments, dict):
        arguments = {}
    try:
        spec = get_tool_authorization(tool_name)
    except Exception:
        return None
    agent_name = payload.get("agent_name")
    mcp_server = payload.get("mcp_server")
    reason = payload.get("reason")
    agent_name_value = (
        agent_name if isinstance(agent_name, str) and agent_name else default_agent_name
    )
    reason_value = (
        reason if isinstance(reason, str) and reason else default_reason
    )
    return ToolIntent(
        agent_name=agent_name_value,
        mcp_server=(
            mcp_server
            if isinstance(mcp_server, str) and mcp_server
            else spec.downstream_audience or "workflow-runtime"
        ),
        tool_name=tool_name,
        arguments=cast(dict[str, object], arguments),
        reason=reason_value,
        metadata_ref=f"{metadata_prefix}:{tool_name}",
    )


def build_default_intent_provider() -> ToolIntentProvider:
    return GoogleAdkToolIntentProvider()


def _extract_hostname(query: str) -> str:
    match = re.search(
        r"\b([A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?(?:\.[A-Za-z0-9-]+)+)\b",
        query,
    )
    return match.group(1) if match else "app.example.com"


def _load_adk_types() -> AdkRuntimeTypes | None:
    try:
        agents_module = import_module("google.adk.agents")
        runners_module = import_module("google.adk.runners")
        sessions_module = import_module("google.adk.sessions")
        genai_types_module = import_module("google.genai.types")
    except ImportError:
        return None
    try:
        anthropic_module = import_module("google.adk.models.anthropic_llm")
    except ImportError:
        anthropic_module = None

    agent_type = getattr(agents_module, "Agent", None)
    anthropic_llm_type = (
        None if anthropic_module is None else getattr(anthropic_module, "AnthropicLlm", None)
    )
    content_type = getattr(genai_types_module, "Content", None)
    part_type = getattr(genai_types_module, "Part", None)
    runner_type = getattr(runners_module, "Runner", None)
    session_service_type = getattr(sessions_module, "InMemorySessionService", None)
    if (
        not isinstance(agent_type, type)
        or not isinstance(content_type, type)
        or not isinstance(part_type, type)
        or not isinstance(runner_type, type)
        or not isinstance(session_service_type, type)
    ):
        return None
    return AdkRuntimeTypes(
        agent_type=agent_type,
        anthropic_llm_type=(
            anthropic_llm_type if isinstance(anthropic_llm_type, type) else None
        ),
        content_type=content_type,
        part_type=part_type,
        runner_type=runner_type,
        session_service_type=session_service_type,
    )


def _adk_user_prompt(
    context: SanitizedWorkflowContext,
    *,
    allowed_tool_names: set[str] | None,
    available_tool_names: set[str],
) -> str:
    allowed_tools: list[str] | None = (
        None if allowed_tool_names is None else sorted(allowed_tool_names)
    )
    return json.dumps(
        {
            "allowed_tools": allowed_tools,
            "available_tools": sorted(available_tool_names),
            "instructions": (
                "Return only JSON with assistant_message and tool_intents. "
                "assistant_message must be concise, user-visible prose. "
                "A tool intent is required when the user request matches an available "
                "allowed tool contract. Use an empty tool_intents array only when no "
                "tool contract matches."
            ),
            "query": context.query,
            "session_id": context.session_id,
            "tenant_id": context.tenant_id,
            "tool_contracts": [
                _tool_contract(tool_name)
                for tool_name in sorted(available_tool_names)
                if allowed_tool_names is None or tool_name in allowed_tool_names
            ],
            "user_id": context.user_id,
        },
        sort_keys=True,
    )


def _extract_adk_event_text(event: object) -> str:
    content = getattr(event, "content", None)
    if content is None:
        return ""
    parts = getattr(content, "parts", None)
    if not isinstance(parts, list):
        return ""

    chunks: list[str] = []
    for part in cast(list[object], parts):
        text = getattr(part, "text", None)
        if isinstance(text, str) and text.strip():
            chunks.append(text.strip())

        function_response = getattr(part, "function_response", None)
        response = getattr(function_response, "response", None)
        if isinstance(response, (dict, list)):
            chunks.append(json.dumps(response, sort_keys=True))
    return "\n".join(chunks)


def _is_adk_final_response(event: object) -> bool:
    is_final_response = getattr(event, "is_final_response", None)
    return bool(is_final_response()) if callable(is_final_response) else False


def _tool_contract(tool_name: str) -> dict[str, object]:
    spec = get_tool_authorization(tool_name)
    return {
        "tool_name": tool_name,
        "description": spec.hitl_description,
        "operation_type": spec.op,
        "required_argument_names": _tool_argument_names(tool_name),
        "downstream_audience": spec.downstream_audience,
    }


def _tool_argument_names(tool_name: str) -> list[str]:
    known_arguments: dict[str, list[str]] = {
        "get_account_balance": ["account_id"],
        "get_developer_app": ["appid"],
        "get_identity_profile": ["subject_user_id"],
        "inspect_dns_record": ["record_name"],
        "inspect_vm": ["vm_id"],
        "propose_workflow_plan": ["query"],
        "restart_vm": ["vm_id"],
        "rotate_vpn_credential": ["credential_id"],
        "update_firewall_rule": ["rule_id", "cidr"],
        "update_iam_binding": ["principal_id", "role"],
    }
    if tool_name in known_arguments:
        return known_arguments[tool_name]
    spec = TOOL_AUTHORIZATION_CATALOG.get(tool_name)
    return [] if spec is None else list(spec.scope_args)
