from __future__ import annotations

from datetime import UTC, datetime

from fxbot.filters.market_hours import check_market_hours


def test_market_closed_returns_rejection_reason():
    result = check_market_hours(datetime(2026, 5, 2, 12, 0, tzinfo=UTC))

    assert not result.allowed
    assert result.reason == "market_closed"


def test_market_open_allows_entry():
    result = check_market_hours(datetime(2026, 5, 4, 12, 0, tzinfo=UTC))

    assert result.allowed
    assert result.reason is None
