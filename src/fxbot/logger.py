from __future__ import annotations

import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from fxbot.db import log_entry_rejection, log_spread_history


def configure_logging(level: str = "INFO") -> logging.Logger:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        stream=sys.stderr,
        force=True,
    )
    return logging.getLogger("fxbot")


ENTRY_REJECTION_REASONS = frozenset(
    {
        "env_mismatch",
        "market_closed",
        "spread_too_high",
        "currency_exposure",
        "exposure_api_failed",
    }
)


def record_entry_rejection(
    db_path: Path,
    *,
    pair: str,
    direction: str,
    reason: str,
    spread: float | None = None,
    spread_threshold: float | None = None,
    atr: float | None = None,
    atr_ratio: float | None = None,
    confluence_kind: str | None = None,
    agreed: str | None = None,
    classes: str | None = None,
    extra: dict[str, Any] | None = None,
) -> bool:
    if reason not in ENTRY_REJECTION_REASONS:
        raise ValueError(f"unsupported entry rejection reason: {reason}")

    return log_entry_rejection(
        db_path,
        pair=pair,
        direction=direction,
        reason=reason,
        spread=spread,
        spread_threshold=spread_threshold,
        atr=atr,
        atr_ratio=atr_ratio,
        confluence_kind=confluence_kind,
        agreed=agreed,
        classes=classes,
        extra=extra,
    )


def record_spread_history(
    db_path: Path,
    *,
    pair: str,
    bid: float,
    ask: float,
    timestamp: datetime | None = None,
) -> bool:
    return log_spread_history(db_path, pair=pair, bid=bid, ask=ask, timestamp=timestamp)
