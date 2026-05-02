from __future__ import annotations

import sqlite3
from datetime import UTC, datetime

from fxbot.config import HARD_SPREAD_CAP
from fxbot.db import init_db
from fxbot.filters.spread import (
    calc_spread_threshold,
    calc_spread_threshold_from_samples,
    check_spread_filter,
)
from fxbot.logger import record_entry_rejection, record_spread_history


def test_spread_sample_shortage_returns_hard_cap():
    spreads = [0.0001] * 99

    threshold = calc_spread_threshold_from_samples("EUR_USD", spreads)

    assert threshold == HARD_SPREAD_CAP["EUR_USD"]


def test_spread_threshold_uses_min_of_p95_and_hard_cap():
    low_spreads = [0.0001] * 100
    high_spreads = [0.0001] * 95 + [0.01] * 5

    assert calc_spread_threshold_from_samples("EUR_USD", low_spreads) == 0.0001
    assert calc_spread_threshold_from_samples("EUR_USD", high_spreads) == HARD_SPREAD_CAP[
        "EUR_USD"
    ]


def test_spread_filter_rejects_spread_above_threshold(tmp_path):
    db_path = tmp_path / "trades.db"
    init_db(db_path)

    result = check_spread_filter(
        pair="EUR_USD",
        current_spread=HARD_SPREAD_CAP["EUR_USD"] + 0.0001,
        db_path=db_path,
        now=datetime(2026, 5, 1, 12, 0, tzinfo=UTC),
    )

    assert not result.allowed
    assert result.reason == "spread_too_high"
    assert result.threshold == HARD_SPREAD_CAP["EUR_USD"]


def test_spread_history_records_bid_ask_and_spread(tmp_path):
    db_path = tmp_path / "trades.db"
    init_db(db_path)

    assert record_spread_history(db_path, pair="EUR_USD", bid=1.1, ask=1.1002)

    with sqlite3.connect(db_path) as conn:
        row = conn.execute("SELECT pair, bid, ask, spread FROM spread_history").fetchone()

    assert row == ("EUR_USD", 1.1, 1.1002, 0.00019999999999997797)


def test_calc_spread_threshold_reads_recent_history(tmp_path):
    db_path = tmp_path / "trades.db"
    init_db(db_path)
    now = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)
    for _ in range(100):
        assert record_spread_history(
            db_path,
            pair="EUR_USD",
            bid=1.1,
            ask=1.1001,
            timestamp=now,
        )

    threshold = calc_spread_threshold("EUR_USD", db_path, now=now)

    assert threshold == 0.00009999999999998899


def test_spread_too_high_entry_rejection_insert(tmp_path):
    db_path = tmp_path / "trades.db"
    init_db(db_path)

    assert record_entry_rejection(
        db_path,
        pair="EUR_USD",
        direction="buy",
        reason="spread_too_high",
        spread=0.001,
        spread_threshold=HARD_SPREAD_CAP["EUR_USD"],
    )

    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT pair, direction, reason, spread, spread_threshold
            FROM entry_rejections
            """
        ).fetchone()

    assert row == ("EUR_USD", "buy", "spread_too_high", 0.001, HARD_SPREAD_CAP["EUR_USD"])
