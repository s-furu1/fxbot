from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Callable

MAX_CURRENCY_RISK = 0.015


@dataclass(frozen=True)
class ExposureFilterResult:
    allowed: bool
    reason: str | None = None


class ExposureCache:
    def __init__(self, ttl_seconds: float = 5.0) -> None:
        self._ttl = ttl_seconds
        self._cached_at: datetime | None = None
        self._cached_value: dict[str, float] | None = None

    def get(
        self,
        fetcher: Callable[[], dict[str, float]],
        now: datetime | None = None,
    ) -> dict[str, float | bool]:
        current = now or datetime.now(UTC)
        if current.tzinfo is None:
            current = current.replace(tzinfo=UTC)
        current = current.astimezone(UTC)

        if (
            self._cached_at is not None
            and self._cached_value is not None
            and (current - self._cached_at).total_seconds() < self._ttl
        ):
            return self._cached_value

        try:
            value = fetcher()
        except Exception:
            # TODO: docs/filters.md allows using a previous cached value after
            # API failure. Phase 3 explicitly requires failure to reject safely.
            return {"_fallback": True}

        self._cached_at = current
        self._cached_value = value
        return value


def check_exposure_filter(
    *,
    pair: str,
    direction: str,
    additional_risk_amount: float,
    equity: float,
    exposure: dict[str, float | bool],
) -> ExposureFilterResult:
    if exposure.get("_fallback"):
        return ExposureFilterResult(allowed=False, reason="exposure_api_failed")
    if equity <= 0:
        return ExposureFilterResult(allowed=False, reason="exposure_api_failed")

    base, quote = pair.split("_", maxsplit=1)
    sign = 1 if direction == "buy" else -1
    add_ratio = additional_risk_amount / equity

    new_base = float(exposure.get(base, 0.0)) + sign * add_ratio
    new_quote = float(exposure.get(quote, 0.0)) - sign * add_ratio

    if abs(new_base) > MAX_CURRENCY_RISK or abs(new_quote) > MAX_CURRENCY_RISK:
        return ExposureFilterResult(allowed=False, reason="currency_exposure")
    return ExposureFilterResult(allowed=True)


def passes_exposure_filter(
    *,
    pair: str,
    direction: str,
    additional_risk_amount: float,
    equity: float,
    exposure_cache: ExposureCache,
    fetcher: Callable[[], dict[str, float]],
    now: datetime | None = None,
) -> ExposureFilterResult:
    exposure = exposure_cache.get(fetcher, now)
    return check_exposure_filter(
        pair=pair,
        direction=direction,
        additional_risk_amount=additional_risk_amount,
        equity=equity,
        exposure=exposure,
    )
