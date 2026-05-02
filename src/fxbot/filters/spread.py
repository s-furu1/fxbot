from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np

from fxbot.config import HARD_SPREAD_CAP
from fxbot.db import query_spreads

MIN_SPREAD_SAMPLES = 100


@dataclass(frozen=True)
class SpreadFilterResult:
    allowed: bool
    threshold: float
    reason: str | None = None


def calc_spread_threshold_from_samples(pair: str, spreads: list[float]) -> float:
    hard_cap = HARD_SPREAD_CAP[pair]
    if len(spreads) < MIN_SPREAD_SAMPLES:
        return hard_cap

    statistical_threshold = float(np.percentile(spreads, 95))
    return min(statistical_threshold, hard_cap)


def calc_spread_threshold(pair: str, db_path: Path, now: datetime | None = None) -> float:
    current = now or datetime.now(UTC)
    if current.tzinfo is None:
        current = current.replace(tzinfo=UTC)
    current = current.astimezone(UTC)

    # TODO: docs/filters.md defines Phase B and spread_thresholds cache,
    # but schema.md does not include that cache table. Keep Phase A only
    # until a migration adds a frozen cache schema.
    spreads = query_spreads(db_path, pair=pair, since=current - timedelta(hours=24))
    return calc_spread_threshold_from_samples(pair, spreads)


def check_spread_filter(
    *,
    pair: str,
    current_spread: float,
    db_path: Path,
    now: datetime | None = None,
) -> SpreadFilterResult:
    threshold = calc_spread_threshold(pair, db_path, now)
    if current_spread > threshold:
        return SpreadFilterResult(
            allowed=False,
            threshold=threshold,
            reason="spread_too_high",
        )
    return SpreadFilterResult(allowed=True, threshold=threshold)
