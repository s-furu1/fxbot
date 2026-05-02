from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fxbot.confluence import ConfluenceKind, evaluate_confluence
from fxbot.strategies.base import Signal, StructureClass


BASE_TIME = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)


def make_signal(
    *,
    source: str,
    structure_class: StructureClass,
    direction: str = "buy",
    issued_at: datetime = BASE_TIME,
    pair: str = "EUR_USD",
) -> Signal:
    return Signal(
        pair=pair,
        direction=direction,
        source=source,
        structure_class=structure_class,
        issued_at=issued_at,
        expiry_seconds=60,
        atr=0.001,
        atr_ratio=1.1,
        spread=0.0001,
        price=1.1,
    )


def test_cross_class_confluence_for_two_structure_classes():
    result = evaluate_confluence(
        "EUR_USD",
        [
            make_signal(source="vol_breakout", structure_class=StructureClass.VOLATILITY),
            make_signal(source="flow_follow", structure_class=StructureClass.FLOW),
        ],
    )

    assert result.kind == ConfluenceKind.CROSS_CLASS
    assert result.is_entry_candidate
    assert result.direction == "buy"
    assert result.signal_count == 2
    assert result.classes == ("flow", "volatility")
    assert result.agreed == ("flow_follow", "vol_breakout")
    assert result.first_signal_time == BASE_TIME
    assert result.last_signal_time == BASE_TIME
    assert result.atr == 0.001
    assert result.atr_ratio == 1.1
    assert result.spread == 0.0001


def test_same_structure_class_two_strategies_is_intraclass_only():
    result = evaluate_confluence(
        "EUR_USD",
        [
            make_signal(source="mean_rev_a", structure_class=StructureClass.REVERSION),
            make_signal(source="mean_rev_b", structure_class=StructureClass.REVERSION),
        ],
    )

    assert result.kind == ConfluenceKind.INTRACLASS_ONLY
    assert not result.is_entry_candidate
    assert result.direction == "buy"
    assert result.classes == ("reversion",)
    assert result.agreed == ("mean_rev_a", "mean_rev_b")


def test_buy_sell_both_cross_class_is_conflicting_signals():
    result = evaluate_confluence(
        "EUR_USD",
        [
            make_signal(
                source="buy_vol",
                structure_class=StructureClass.VOLATILITY,
                direction="buy",
            ),
            make_signal(source="buy_flow", structure_class=StructureClass.FLOW, direction="buy"),
            make_signal(
                source="sell_vol",
                structure_class=StructureClass.VOLATILITY,
                direction="sell",
            ),
            make_signal(source="sell_flow", structure_class=StructureClass.FLOW, direction="sell"),
        ],
    )

    assert result.kind == ConfluenceKind.CONFLICTING_SIGNALS
    assert not result.is_entry_candidate
    assert result.direction is None
    assert result.signal_count == 4
    assert result.classes == ("flow", "volatility")
    assert result.agreed == ("buy_flow", "buy_vol", "sell_flow", "sell_vol")


def test_no_confluence_for_single_signal():
    result = evaluate_confluence(
        "EUR_USD",
        [make_signal(source="vol_breakout", structure_class=StructureClass.VOLATILITY)],
    )

    assert result.kind == ConfluenceKind.NO_CONFLUENCE
    assert not result.is_entry_candidate
    assert result.signal_count == 0


def test_expired_signals_passed_directly_do_not_create_cross_class():
    result = evaluate_confluence(
        "EUR_USD",
        [
            make_signal(
                source="old_vol",
                structure_class=StructureClass.VOLATILITY,
                issued_at=BASE_TIME,
            ),
            make_signal(
                source="old_flow",
                structure_class=StructureClass.FLOW,
                issued_at=BASE_TIME,
            ),
        ],
        now=BASE_TIME + timedelta(seconds=61),
    )

    assert result.kind == ConfluenceKind.NO_CONFLUENCE
    assert not result.is_entry_candidate


def test_confluence_uses_latest_signal_metrics():
    latest = BASE_TIME + timedelta(seconds=10)
    result = evaluate_confluence(
        "EUR_USD",
        [
            make_signal(source="vol_breakout", structure_class=StructureClass.VOLATILITY),
            Signal(
                pair="EUR_USD",
                direction="buy",
                source="flow_follow",
                structure_class=StructureClass.FLOW,
                issued_at=latest,
                expiry_seconds=60,
                atr=0.002,
                atr_ratio=1.3,
                spread=0.0002,
                price=1.2,
            ),
        ],
    )

    assert result.kind == ConfluenceKind.CROSS_CLASS
    assert result.first_signal_time == BASE_TIME
    assert result.last_signal_time == latest
    assert result.atr == 0.002
    assert result.atr_ratio == 1.3
    assert result.spread == 0.0002
