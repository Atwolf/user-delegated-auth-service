from __future__ import annotations

import pytest
from pydantic import ValidationError
from token_broker import TokenExchangeRequest, TokenExchangeResponse


def test_exchange_request_deduplicates_and_trims_scopes() -> None:
    request = TokenExchangeRequest(
        subject_token="incoming-token",
        requested_scopes=[
            " DOE.Developer.ABCD ",
            "DOE.Developer.ABCD",
            "DOE.Billing.XYZ",
        ],
    )

    assert request.requested_scopes == (
        "DOE.Developer.ABCD",
        "DOE.Billing.XYZ",
    )


@pytest.mark.parametrize(
    "scopes",
    [
        [],
        [""],
        ["DOE.Developer.ABCD", "   "],
        "DOE.Developer.ABCD",
    ],
)
def test_exchange_request_rejects_invalid_scope_inputs(scopes: object) -> None:
    with pytest.raises(ValidationError):
        TokenExchangeRequest(
            subject_token="incoming-token",
            requested_scopes=scopes,
        )


def test_exchange_request_repr_does_not_include_subject_token() -> None:
    request = TokenExchangeRequest(
        subject_token="secret-subject-token",
        requested_scopes=["DOE.Developer.ABCD"],
    )

    assert "secret-subject-token" not in repr(request)


def test_exchange_response_returns_raw_token_but_masks_repr() -> None:
    response = TokenExchangeResponse(
        access_token="raw-access-token",
        scopes=["DOE.Developer.ABCD"],
    )

    assert response.access_token == "raw-access-token"
    assert response.model_dump()["access_token"] == "raw-access-token"
    assert "raw-access-token" not in repr(response)


def test_exchange_response_rejects_empty_access_token() -> None:
    with pytest.raises(ValidationError):
        TokenExchangeResponse(access_token="")
