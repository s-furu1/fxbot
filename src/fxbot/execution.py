from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fxbot.confluence import ConfluenceKind, ConfluenceResult
from fxbot.logger import record_entry_rejection


class ExecutionError(RuntimeError):
    """Raised when execution is unsafe or unsupported."""


@dataclass(frozen=True)
class VerificationState:
    verified: bool


@dataclass(frozen=True)
class OrderRequest:
    pair: str
    direction: str
    units: int
    entry_price: float
    sl_price: float
    tp_price: float
    risk_amount: float
    risk_ratio: float
    confluence_result: ConfluenceResult

    def __post_init__(self) -> None:
        if self.units <= 0:
            raise ExecutionError("units must be greater than zero")
        if self.sl_price is None:
            raise ExecutionError("sl_price is required")
        if self.tp_price is None:
            raise ExecutionError("tp_price is required")


@dataclass(frozen=True)
class DryRunOrderResult:
    dry_run: bool
    planned_order: dict[str, Any]
    persisted_to_opens: bool = False


def is_environment_verified(verification_state: VerificationState) -> bool:
    return verification_state.verified


def place_order(
    request: OrderRequest,
    *,
    verification_state: VerificationState,
    dry_run: bool = True,
    db_path: Path | None = None,
) -> DryRunOrderResult:
    if not is_environment_verified(verification_state):
        _record_env_mismatch(request, db_path)
        raise ExecutionError("environment is not verified")

    _validate_order_request(request)

    if not dry_run:
        raise ExecutionError("live order execution is not implemented")

    planned_order = _planned_order_payload(request)
    logging.getLogger("fxbot.execution").info("dry-run order planned", extra=planned_order)
    return DryRunOrderResult(
        dry_run=True,
        planned_order=planned_order,
        persisted_to_opens=False,
    )


def _validate_order_request(request: OrderRequest) -> None:
    if request.direction not in {"buy", "sell"}:
        raise ExecutionError("direction must be buy or sell")
    if request.units <= 0:
        raise ExecutionError("units must be greater than zero")
    if request.sl_price is None:
        raise ExecutionError("sl_price is required")
    if request.tp_price is None:
        raise ExecutionError("tp_price is required")
    if request.confluence_result.kind != ConfluenceKind.CROSS_CLASS:
        raise ExecutionError("only cross-class confluence can be executed")
    if not request.confluence_result.is_entry_candidate:
        raise ExecutionError("confluence result is not an entry candidate")


def _planned_order_payload(request: OrderRequest) -> dict[str, Any]:
    return {
        "pair": request.pair,
        "direction": request.direction,
        "units": request.units,
        "entry_price": request.entry_price,
        "sl_price": request.sl_price,
        "tp_price": request.tp_price,
        "risk_amount": request.risk_amount,
        "risk_ratio": request.risk_ratio,
        "confluence": {
            "kind": request.confluence_result.kind.value,
            "signal_count": request.confluence_result.signal_count,
            "classes": request.confluence_result.classes,
            "agreed": request.confluence_result.agreed,
            "first_signal_time": (
                request.confluence_result.first_signal_time.isoformat()
                if request.confluence_result.first_signal_time
                else None
            ),
            "last_signal_time": (
                request.confluence_result.last_signal_time.isoformat()
                if request.confluence_result.last_signal_time
                else None
            ),
            "atr": request.confluence_result.atr,
            "atr_ratio": request.confluence_result.atr_ratio,
            "spread": request.confluence_result.spread,
        },
    }


def _record_env_mismatch(request: OrderRequest, db_path: Path | None) -> None:
    if db_path is None:
        return

    record_entry_rejection(
        db_path,
        pair=request.pair,
        direction=request.direction,
        reason="env_mismatch",
        spread=request.confluence_result.spread,
        atr=request.confluence_result.atr,
        atr_ratio=request.confluence_result.atr_ratio,
        confluence_kind=request.confluence_result.kind.value,
        agreed=",".join(request.confluence_result.agreed),
        classes=",".join(request.confluence_result.classes),
    )
