from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TypeAlias, TypeVar, cast

from pydantic import BaseModel

from a2a_runtime.errors import (
    InvalidA2APayloadContractError,
    UnknownA2AActionError,
)
from a2a_runtime.models import A2AEnvelope

PayloadModelT = TypeVar("PayloadModelT", bound=BaseModel)
ActionPayloadContracts: TypeAlias = Mapping[str, type[BaseModel]]


def validate_payload(
    payload: Any,
    payload_model: type[PayloadModelT],
) -> PayloadModelT:
    """Validate one raw payload against a strict Pydantic action contract."""

    _ensure_strict_payload_model(payload_model)
    return payload_model.model_validate(payload, strict=True)


def validate_payload_for_action(
    action: str,
    payload: Any,
    contracts: ActionPayloadContracts,
) -> BaseModel:
    """Validate one raw payload using the contract registered for an action."""

    payload_model = payload_model_for_action(action, contracts)
    return validate_payload(payload, payload_model)


def validate_envelope_for_action(
    action: str,
    envelope: Mapping[str, Any] | A2AEnvelope[Any],
    contracts: ActionPayloadContracts,
) -> A2AEnvelope[BaseModel]:
    """Validate an A2A envelope and coerce its payload to the action contract."""

    payload_model = payload_model_for_action(action, contracts)
    data = _envelope_data(envelope)

    if "payload" in data:
        data["payload"] = validate_payload(data["payload"], payload_model)

    envelope_model = _typed_envelope_model(payload_model)
    return envelope_model.model_validate(data)


def payload_model_for_action(
    action: str,
    contracts: ActionPayloadContracts,
) -> type[BaseModel]:
    if not action:
        raise UnknownA2AActionError("A2A action must be a non-empty string")

    try:
        payload_model = contracts[action]
    except KeyError as exc:
        raise UnknownA2AActionError(
            f"No A2A payload contract registered for action {action!r}"
        ) from exc

    _ensure_strict_payload_model(payload_model)
    return payload_model


def _ensure_strict_payload_model(payload_model: type[BaseModel]) -> None:
    if payload_model.model_config.get("extra") != "forbid":
        raise InvalidA2APayloadContractError(
            f"{payload_model.__name__} must set model_config extra='forbid'"
        )

    if payload_model.model_config.get("strict") is not True:
        raise InvalidA2APayloadContractError(
            f"{payload_model.__name__} must set model_config strict=True"
        )


def _envelope_data(envelope: Mapping[str, Any] | A2AEnvelope[Any]) -> dict[str, Any]:
    if isinstance(envelope, BaseModel):
        return envelope.model_dump()

    return dict(envelope)


def _typed_envelope_model(
    payload_model: type[BaseModel],
) -> type[A2AEnvelope[BaseModel]]:
    return cast(
        type[A2AEnvelope[BaseModel]],
        A2AEnvelope.__class_getitem__(payload_model),
    )
