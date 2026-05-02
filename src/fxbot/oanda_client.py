from __future__ import annotations

from typing import Any

from oandapyV20 import API
from oandapyV20.endpoints.accounts import AccountSummary
from oandapyV20.endpoints.instruments import InstrumentsCandles
from oandapyV20.endpoints.positions import OpenPositions
from oandapyV20.endpoints.pricing import PricingInfo


class OandaClientError(RuntimeError):
    """Raised when a read-only OANDA API call fails."""


class OandaReadOnlyClient:
    """Small read-only wrapper around the OANDA v20 REST API."""

    def __init__(
        self,
        *,
        api_key: str,
        account_id: str,
        environment: str,
        request_timeout: float = 10.0,
        api: Any | None = None,
    ) -> None:
        self.account_id = account_id
        self._api = api or API(
            access_token=api_key,
            environment=environment,
            request_params={"timeout": request_timeout},
        )

    def _request(self, endpoint: Any) -> dict[str, Any]:
        try:
            response = self._api.request(endpoint)
        except Exception as exc:
            raise OandaClientError(f"OANDA read-only request failed: {exc}") from exc
        if not isinstance(response, dict):
            raise OandaClientError("OANDA response was not a JSON object")
        return response

    def get_account_summary(self) -> dict[str, Any]:
        response = self._request(AccountSummary(self.account_id))
        account = response.get("account")
        if not isinstance(account, dict):
            raise OandaClientError("AccountSummary response did not include account")
        return account

    def list_open_positions(self) -> list[dict[str, Any]]:
        response = self._request(OpenPositions(self.account_id))
        positions = response.get("positions")
        if not isinstance(positions, list):
            raise OandaClientError("OpenPositions response did not include positions")
        return positions

    def get_candles(
        self,
        instrument: str,
        *,
        granularity: str = "M1",
        count: int = 500,
        price: str = "M",
    ) -> list[dict[str, Any]]:
        params = {
            "granularity": granularity,
            "count": count,
            "price": price,
        }
        response = self._request(InstrumentsCandles(instrument=instrument, params=params))
        candles = response.get("candles")
        if not isinstance(candles, list):
            raise OandaClientError("InstrumentsCandles response did not include candles")
        return candles

    def get_pricing(self, instruments: list[str]) -> list[dict[str, Any]]:
        params = {"instruments": ",".join(instruments)}
        response = self._request(PricingInfo(accountID=self.account_id, params=params))
        prices = response.get("prices")
        if not isinstance(prices, list):
            raise OandaClientError("PricingInfo response did not include prices")
        return prices
