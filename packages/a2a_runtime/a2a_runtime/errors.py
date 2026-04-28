from __future__ import annotations


class A2AContractError(Exception):
    """Base error for invalid A2A runtime contract configuration."""


class UnknownA2AActionError(A2AContractError):
    """Raised when no typed payload contract is registered for an action."""


class InvalidA2APayloadContractError(A2AContractError):
    """Raised when a registered payload contract is not strict enough."""
