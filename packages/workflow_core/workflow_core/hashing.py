from __future__ import annotations

import hashlib
import json
from typing import Any

from pydantic import BaseModel

from workflow_core.models import WorkflowPlan


def canonical_json(model: BaseModel) -> str:
    payload: dict[str, Any] = model.model_dump(
        mode="json",
        exclude_none=True,
        by_alias=False,
    )
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def plan_hash(plan: WorkflowPlan) -> str:
    digest = hashlib.sha256(canonical_json(plan).encode("utf-8")).hexdigest()
    return f"sha256:{digest}"
