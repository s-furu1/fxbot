from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta

from fxbot.confluence import ConfluenceKind, evaluate_confluence
from fxbot.db import init_db
from fxbot.logger import record_entry_rejection
from fxbot.signal_bus import DEFAULT_SYNC_WINDOW_SECONDS, SignalBus
from fxbot.strategies.base import Signal, StructureClass


BASE_TIME = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)


def make_signal(
    *,
    source: str,
    structure_class: StructureClass,
    issued_at: datetime = BASE_TIME,
    direction: str = "buy",
    expiry_seconds: int = DEFAULT_SYNC_WINDOW_SECONDS,
) -> Signal:
    return Signal(
        pair="EUR_USD",
        direction=direction,
        source=source,
        structure_class=structure_class,
        issued_at=issued_at,
        expiry_seconds=expiry_seconds,
        atr=0.001,
        atr_ratio=1.1,
        spread=0.0001,
        price=1.1,
    )


def test_signal_bus_persists_signal_to_signals_table(tmp_path):
    db_path = tmp_path / "trades.db"
    init_db(db_path)
    bus = SignalBus(db_path)

    assert bus.publish(
        make_signal(source="vol_breakout", structure_class=StructureClass.VOLATILITY)
    )

    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT timestamp, pair, source, structure_class, direction,
                   price, atr, atr_ratio, spread
            FROM signals
            """
        ).fetchone()

    assert row == (
        BASE_TIME.isoformat(),
        "EUR_USD",
        "vol_breakout",
        "volatility",
        "buy",
        1.1,
        0.001,
        1.1,
        0.0001,
    )


def test_signal_bus_returns_pair_active_signals_only(tmp_path):
    db_path = tmp_path / "trades.db"
    init_db(db_path)
    bus = SignalBus(db_path)
    active = make_signal(source="active", structure_class=StructureClass.VOLATILITY)
    other_pair = Signal(
        pair="USD_JPY",
        direction="buy",
        source="other",
        structure_class=StructureClass.FLOW,
        issued_at=BASE_TIME,
        expiry_seconds=60,
        atr=0.1,
        atr_ratio=1.0,
        spread=0.01,
        price=150.0,
    )

    bus.publish(active)
    bus.publish(other_pair)

    assert bus.get_active_signals("EUR_USD", now=BASE_TIME + timedelta(seconds=30)) == [active]


def test_signal_older_than_60_seconds_is_inactive(tmp_path):
    db_path = tmp_path / "trades.db"
    init_db(db_path)
    bus = SignalBus(db_path)
    expired = make_signal(source="expired", structure_class=StructureClass.VOLATILITY)
    active = make_signal(
        source="active",
        structure_class=StructureClass.FLOW,
        issued_at=BASE_TIME + timedelta(seconds=2),
    )

    bus.publish(expired)
    bus.publish(active)

    active_signals = bus.get_active_signals("EUR_USD", now=BASE_TIME + timedelta(seconds=61))

    assert active_signals == [active]


def test_expired_signal_is_not_confluence_candidate(tmp_path):
    db_path = tmp_path / "trades.db"
    init_db(db_path)
    bus = SignalBus(db_path)
    bus.publish(make_signal(source="expired_vol", structure_class=StructureClass.VOLATILITY))
    bus.publish(
        make_signal(
            source="active_flow",
            structure_class=StructureClass.FLOW,
            issued_at=BASE_TIME + timedelta(seconds=2),
        )
    )

    active_signals = bus.get_active_signals("EUR_USD", now=BASE_TIME + timedelta(seconds=61))
    result = evaluate_confluence("EUR_USD", active_signals)

    assert result.kind == ConfluenceKind.NO_CONFLUENCE
    assert not result.is_entry_candidate


def test_intraclass_only_can_be_recorded_as_entry_rejection(tmp_path):
    db_path = tmp_path / "trades.db"
    init_db(db_path)
    result = evaluate_confluence(
        "EUR_USD",
        [
            make_signal(source="rev_a", structure_class=StructureClass.REVERSION),
            make_signal(source="rev_b", structure_class=StructureClass.REVERSION),
        ],
    )

    assert result.kind == ConfluenceKind.INTRACLASS_ONLY
    assert record_entry_rejection(
        db_path,
        pair=result.pair,
        direction=result.direction or "none",
        reason=result.kind.value,
        confluence_kind=result.kind.value,
        agreed=",".join(result.agreed),
        classes=",".join(result.classes),
    )

    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT reason, confluence_kind, agreed, classes
            FROM entry_rejections
            """
        ).fetchone()

    assert row == ("intraclass_only", "intraclass_only", "rev_a,rev_b", "reversion")
