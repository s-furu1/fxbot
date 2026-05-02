from __future__ import annotations

from datetime import UTC, datetime

from fxbot.filters.exposure import ExposureCache, check_exposure_filter, passes_exposure_filter


def test_exposure_fetch_failure_rejects_safely():
    cache = ExposureCache()

    def failing_fetcher():
        raise RuntimeError("api unavailable")

    result = passes_exposure_filter(
        pair="EUR_USD",
        direction="buy",
        additional_risk_amount=100,
        equity=10_000,
        exposure_cache=cache,
        fetcher=failing_fetcher,
        now=datetime(2026, 5, 1, 12, 0, tzinfo=UTC),
    )

    assert not result.allowed
    assert result.reason == "exposure_api_failed"


def test_exposure_limit_rejects_currency_concentration():
    result = check_exposure_filter(
        pair="EUR_USD",
        direction="buy",
        additional_risk_amount=100,
        equity=10_000,
        exposure={"EUR": 0.01, "USD": 0.0},
    )

    assert not result.allowed
    assert result.reason == "currency_exposure"


def test_exposure_within_limit_allows_entry():
    result = check_exposure_filter(
        pair="EUR_USD",
        direction="buy",
        additional_risk_amount=25,
        equity=10_000,
        exposure={"EUR": 0.0, "USD": 0.0},
    )

    assert result.allowed
    assert result.reason is None
