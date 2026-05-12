from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Literal, cast

from workflow_core import (
    TOOL_AUTHORIZATION_CATALOG,
    ScopeMaterializationError,
    ToolIntent,
    ToolProposal,
    WorkflowPolicyDecision,
    WorkflowStep,
    evaluate_workflow_policy,
    get_tool_authorization,
    materialize_scopes_for_proposal,
    scope_requirements_for_auth0_token,
    scope_requirements_for_tool,
)

from .models import PlanWorkflowRequest, SanitizedWorkflowContext
from .providers import ToolIntentProvider


@dataclass(frozen=True)
class DispatchResult:
    tool_intents: list[ToolIntent]
    steps: list[WorkflowStep]
    policy: WorkflowPolicyDecision


class WorkflowCoordinator:
    """Coordinates Agent Runtime output without granting execution authority."""

    def __init__(
        self,
        *,
        intent_provider: ToolIntentProvider,
    ) -> None:
        self._intent_provider = intent_provider

    async def propose(self, request: PlanWorkflowRequest) -> list[ToolIntent]:
        context = SanitizedWorkflowContext.from_request(request)
        return _dedupe_intents(
            await self._intent_provider.propose(
                context,
                allowed_tool_names=allowed_tool_names(context.allowed_tools),
                available_tool_names=available_tool_names(),
            )
        )


class ToolIntentDispatcher:
    """Converts advisory intents into workflow_core steps after server validation."""

    def dispatch(
        self,
        request: PlanWorkflowRequest,
        tool_intents: list[ToolIntent],
    ) -> DispatchResult:
        allowed = allowed_tool_names(request.allowed_tools)
        validated_intents: list[ToolIntent] = []
        steps: list[WorkflowStep] = []
        seen: set[str] = set()
        for intent in tool_intents:
            normalized = normalize_tool_intent(intent)
            if normalized is None:
                continue
            if allowed is not None and normalized.tool_name not in allowed:
                continue
            material = _intent_material(normalized)
            if material in seen:
                continue
            try:
                step = step_from_intent(len(steps) + 1, normalized, request.token_scopes)
            except ScopeMaterializationError:
                continue
            seen.add(material)
            validated_intents.append(normalized)
            steps.append(step)
        return DispatchResult(
            tool_intents=validated_intents,
            steps=steps,
            policy=evaluate_workflow_policy(steps),
        )


def available_tool_names() -> set[str]:
    return set(TOOL_AUTHORIZATION_CATALOG)


def allowed_tool_names(allowed_tools: list[str] | None) -> set[str] | None:
    if allowed_tools is None:
        return None
    return set(allowed_tools)


def normalize_tool_intent(intent: ToolIntent) -> ToolIntent | None:
    if intent.tool_name not in available_tool_names():
        return None
    spec = get_tool_authorization(intent.tool_name)
    return intent.model_copy(
        update={
            "mcp_server": spec.downstream_audience or "workflow-runtime",
            "metadata_ref": (
                intent.metadata_ref
                if intent.metadata_ref.startswith("tool_catalog:")
                else f"{intent.metadata_ref}|validated:{intent.tool_name}"
            ),
        }
    )


def step_from_intent(index: int, intent: ToolIntent, token_scopes: list[str]) -> WorkflowStep:
    spec = get_tool_authorization(intent.tool_name)
    proposal = ToolProposal(
        agent_name=intent.agent_name,
        tool_name=intent.tool_name,
        arguments=intent.arguments,
        reason=intent.reason,
    )
    required_scopes = materialize_scopes_for_proposal(
        proposal,
        (
            scope_requirements_for_auth0_token(intent.tool_name, token_scopes)
            if token_scopes
            else scope_requirements_for_tool(intent.tool_name)
        ),
    )
    return WorkflowStep(
        step_id=f"step-{index}",
        target_agent=intent.agent_name,
        action=intent.tool_name,
        input_model_type=f"{intent.tool_name}.arguments",
        input_payload_json=json.dumps(intent.arguments, sort_keys=True, separators=(",", ":")),
        required_scopes=required_scopes,
        downstream_audience=spec.downstream_audience,
        operation_type=cast(Literal["READ", "WRITE", "ADMIN"], spec.op),
        blast_radius=spec.blast_radius,
        hitl_description=spec.hitl_description,
        mutates_external_state=spec.op in {"WRITE", "ADMIN"},
    )


def _dedupe_intents(tool_intents: list[ToolIntent]) -> list[ToolIntent]:
    deduped: list[ToolIntent] = []
    seen: set[str] = set()
    for intent in tool_intents:
        material = _intent_material(intent)
        if material in seen:
            continue
        seen.add(material)
        deduped.append(intent)
    return deduped


def _intent_material(intent: ToolIntent) -> str:
    return json.dumps(
        {
            "arguments": intent.arguments,
            "mcp_server": intent.mcp_server,
            "tool_name": intent.tool_name,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
