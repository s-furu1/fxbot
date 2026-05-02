from __future__ import annotations

import pytest

from fxbot.oanda_client import OandaClientError, OandaReadOnlyClient


class FakeApi:
    def __init__(self, responses):
        self.responses = list(responses)
        self.endpoints = []

    def request(self, endpoint):
        self.endpoints.append(endpoint)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def test_get_account_summary_uses_read_only_summary_endpoint():
    api = FakeApi([{"account": {"id": "101-001-12345678-001"}}])
    client = OandaReadOnlyClient(
        api_key="dummy",
        account_id="101-001-12345678-001",
        environment="practice",
        api=api,
    )

    assert client.get_account_summary() == {"id": "101-001-12345678-001"}
    assert str(api.endpoints[0]) == "v3/accounts/101-001-12345678-001/summary"
    assert api.endpoints[0].method == "GET"


def test_list_open_positions_uses_read_only_open_positions_endpoint():
    api = FakeApi([{"positions": []}])
    client = OandaReadOnlyClient(
        api_key="dummy",
        account_id="101-001-12345678-001",
        environment="practice",
        api=api,
    )

    assert client.list_open_positions() == []
    assert str(api.endpoints[0]) == "v3/accounts/101-001-12345678-001/openPositions"
    assert api.endpoints[0].method == "GET"


def test_get_candles_uses_read_only_candles_endpoint():
    api = FakeApi([{"candles": [{"complete": True}]}])
    client = OandaReadOnlyClient(
        api_key="dummy",
        account_id="101-001-12345678-001",
        environment="practice",
        api=api,
    )

    assert client.get_candles("EUR_USD", count=10) == [{"complete": True}]
    assert str(api.endpoints[0]) == "v3/instruments/EUR_USD/candles"
    assert api.endpoints[0].method == "GET"
    assert api.endpoints[0].params["count"] == 10


def test_get_pricing_uses_read_only_pricing_endpoint():
    api = FakeApi([{"prices": [{"instrument": "EUR_USD"}]}])
    client = OandaReadOnlyClient(
        api_key="dummy",
        account_id="101-001-12345678-001",
        environment="practice",
        api=api,
    )

    assert client.get_pricing(["EUR_USD", "USD_JPY"]) == [{"instrument": "EUR_USD"}]
    assert str(api.endpoints[0]) == "v3/accounts/101-001-12345678-001/pricing"
    assert api.endpoints[0].method == "GET"
    assert api.endpoints[0].params["instruments"] == "EUR_USD,USD_JPY"


def test_oanda_request_error_is_wrapped():
    api = FakeApi([RuntimeError("boom")])
    client = OandaReadOnlyClient(
        api_key="dummy",
        account_id="101-001-12345678-001",
        environment="practice",
        api=api,
    )

    with pytest.raises(OandaClientError):
        client.get_account_summary()
