from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime


@dataclass(frozen=True)
class FilterResult:
    allowed: bool
    reason: str | None = None


def is_market_open(now: datetime | None = None) -> bool:
    current = now or datetime.now(UTC)
    if current.tzinfo is None:
        current = current.replace(tzinfo=UTC)
    current = current.astimezone(UTC)

    weekday = current.weekday()
    if weekday < 4:
        return True
    if weekday == 4:
        return current.hour < 22
    if weekday == 6:
        return current.hour >= 22
    return False


def check_market_hours(now: datetime | None = None) -> FilterResult:
    if is_market_open(now):
        return FilterResult(allowed=True)
    return FilterResult(allowed=False, reason="market_closed")
