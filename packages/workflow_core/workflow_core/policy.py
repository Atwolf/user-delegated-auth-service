from __future__ import annotations

from collections.abc import Sequence
from typing import Literal, cast

from workflow_core.models import WorkflowPolicyDecision, WorkflowStep

BlastRadius = Literal["none", "low", "medium", "high"]
_BLAST_RANK = {"none": 0, "low": 1, "medium": 2, "high": 3}
_RANK_BLAST: dict[int, BlastRadius] = {
    rank: cast(BlastRadius, blast) for blast, rank in _BLAST_RANK.items()
}


def evaluate_workflow_policy(steps: Sequence[WorkflowStep]) -> WorkflowPolicyDecision:
    if not steps:
        return WorkflowPolicyDecision(
            requires_hitl=False,
            blast_radius="none",
            human_description="No workflow actions were proposed.",
            required_scopes=[],
        )

    max_rank = max(_BLAST_RANK[step.blast_radius] for step in steps)
    mutating = any(step.mutates_external_state for step in steps)
    elevated_operation = any(step.operation_type in {"WRITE", "ADMIN"} for step in steps)
    requires_hitl = mutating or elevated_operation or max_rank >= _BLAST_RANK["medium"]
    descriptions = [step.hitl_description for step in steps]

    return WorkflowPolicyDecision(
        requires_hitl=requires_hitl,
        blast_radius=_RANK_BLAST[max_rank],
        human_description="; ".join(descriptions),
        required_scopes=[scope for step in steps for scope in step.required_scopes],
    )
