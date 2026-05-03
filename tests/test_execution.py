from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest

from fxbot.confluence import ConfluenceKind, ConfluenceResult
from fxbot.db import init_db
from fxbot.execution import ExecutionError, OrderRequest, VerificationState, place_order


BASE_TIME = datetime(2026, 5, 1, 12, 0, tzinfo=UTC)


def cross_class_result() -> ConfluenceResult:
    return ConfluenceResult(
        pair="EUR_USD",
        direction="buy",
        kind=ConfluenceKind.CROSS_CLASS,
        signal_count=2,
        classes=("flow", "volatility"),
        agreed=("flow_follow", "vol_breakout"),
        first_signal_time=BASE_TIME,
        last_signal_time=BASE_TIME,
        atr=0.001,
        atr_ratio=1.1,
        spread=0.0001,
    )


def order_request(**overrides) -> OrderRequest:
    values = {
        "pair": "EUR_USD",
        "direction": "buy",
        "units": 1000,
        "entry_price": 1.1,
        "sl_price": 1.09,
        "tp_price": 1.12,
        "risk_amount": 100.0,
        "risk_ratio": 0.01,
        "confluence_result": cross_class_result(),
    }
    values.update(overrides)
    return OrderRequest(**values)


def malformed_order_request(**overrides) -> OrderRequest:
    request = order_request()
    for name, value in overrides.items():
        object.__setattr__(request, name, value)
    return request


def test_dry_run_returns_planned_order_without_api_call():
    result = place_order(
        order_request(),
        verification_state=VerificationState(verified=True),
        dry_run=True,
    )

    assert result.dry_run
    assert not result.persisted_to_opens
    assert result.planned_order["pair"] == "EUR_USD"
    assert result.planned_order["sl_price"] == 1.09
    assert result.planned_order["tp_price"] == 1.12
    assert result.planned_order["confluence"]["kind"] == "cross-class"


def test_dry_run_false_stops_as_not_implemented():
    with pytest.raises(ExecutionError, match="not implemented"):
        place_order(
            order_request(),
            verification_state=VerificationState(verified=True),
            dry_run=False,
        )


def test_order_request_missing_sl_is_rejected():
    with pytest.raises(ExecutionError, match="sl_price"):
        order_request(sl_price=None)


def test_order_request_missing_tp_is_rejected():
    with pytest.raises(ExecutionError, match="tp_price"):
        order_request(tp_price=None)


@pytest.mark.parametrize("units", [0, -1])
def test_order_request_non_positive_units_are_rejected(units):
    with pytest.raises(ExecutionError, match="units"):
        order_request(units=units)


def test_unverified_environment_rejects_with_env_mismatch(tmp_path):
    db_path = tmp_path / "trades.db"
    init_db(db_path)

    with pytest.raises(ExecutionError, match="environment is not verified"):
        place_order(
            order_request(),
            verification_state=VerificationState(verified=False),
            dry_run=True,
            db_path=db_path,
        )

    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT pair, direction, reason, spread, atr, atr_ratio, confluence_kind,
                   agreed, classes
            FROM entry_rejections
            """
        ).fetchone()

    assert row == (
        "EUR_USD",
        "buy",
        "env_mismatch",
        0.0001,
        0.001,
        1.1,
        "cross-class",
        "flow_follow,vol_breakout",
        "flow,volatility",
    )


def test_unverified_environment_rejects_before_live_execution_path():
    with pytest.raises(ExecutionError, match="environment is not verified"):
        place_order(
            order_request(),
            verification_state=VerificationState(verified=False),
            dry_run=False,
        )


def test_unverified_environment_takes_priority_over_missing_sl(tmp_path):
    db_path = tmp_path / "trades.db"
    init_db(db_path)

    with pytest.raises(ExecutionError, match="environment is not verified"):
        place_order(
            malformed_order_request(sl_price=None),
            verification_state=VerificationState(verified=False),
            db_path=db_path,
        )

    with sqlite3.connect(db_path) as conn:
        row = conn.execute("SELECT reason FROM entry_rejections").fetchone()

    assert row == ("env_mismatch",)


def test_unverified_environment_takes_priority_over_invalid_units(tmp_path):
    db_path = tmp_path / "trades.db"
    init_db(db_path)

    with pytest.raises(ExecutionError, match="environment is not verified"):
        place_order(
            malformed_order_request(units=0),
            verification_state=VerificationState(verified=False),
            db_path=db_path,
        )

    with sqlite3.connect(db_path) as conn:
        row = conn.execute("SELECT reason FROM entry_rejections").fetchone()

    assert row == ("env_mismatch",)


def test_non_cross_class_confluence_is_rejected():
    request = order_request(
        confluence_result=ConfluenceResult(
            pair="EUR_USD",
            direction="buy",
            kind=ConfluenceKind.INTRACLASS_ONLY,
            signal_count=2,
            classes=("reversion",),
            agreed=("rev_a", "rev_b"),
            first_signal_time=BASE_TIME,
            last_signal_time=BASE_TIME,
            atr=0.001,
            atr_ratio=1.0,
            spread=0.0001,
        )
    )

    with pytest.raises(ExecutionError, match="cross-class"):
        place_order(request, verification_state=VerificationState(verified=True))


def test_no_oanda_order_or_position_endpoint_imports_in_execution():
    source = Path("src/fxbot/execution.py").read_text(encoding="utf-8")
    forbidden = [
        "oandapyV20.endpoints." + "orders",
        "oandapyV20.endpoints." + "positions",
        "Market" + "Order",
        "Limit" + "Order",
        "Stop" + "Order",
        "Position" + "Close",
        "Trade" + "Close",
    ]

    assert all(token not in source for token in forbidden)
