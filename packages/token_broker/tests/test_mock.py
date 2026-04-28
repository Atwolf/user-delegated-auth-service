from __future__ import annotations

import asyncio

from token_broker import MockTokenBrokerClient, TokenExchangeRequest


def test_mock_exchange_returns_raw_access_token_and_requested_scopes(
    caplog,
) -> None:
    request = TokenExchangeRequest(
        subject_token="incoming-token",
        requested_scopes=["DOE.Developer.ABCD"],
    )
    client = MockTokenBrokerClient(access_token="raw-mock-token")

    response = asyncio.run(client.exchange_token(request))

    assert response.access_token == "raw-mock-token"
    assert response.scopes == ("DOE.Developer.ABCD",)
    assert "raw-mock-token" not in repr(response)
    assert "raw-mock-token" not in caplog.text


def test_mock_exchange_can_derive_token_from_request() -> None:
    request = TokenExchangeRequest(
        subject_token="incoming-token",
        requested_scopes=["DOE.Developer.ABCD", "DOE.Billing.XYZ"],
    )
    client = MockTokenBrokerClient(
        access_token=lambda token_request: (
            "raw-token-for-" + "-".join(token_request.requested_scopes)
        ),
        expires_in=None,
    )

    response = asyncio.run(client.exchange_token(request))

    assert response.access_token == "raw-token-for-DOE.Developer.ABCD-DOE.Billing.XYZ"
    assert response.expires_in is None
