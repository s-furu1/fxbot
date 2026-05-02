from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from fxbot.db import log_signal
from fxbot.strategies.base import Signal

DEFAULT_SYNC_WINDOW_SECONDS = 60


class SignalBus:
    def __init__(self, db_path: Path) -> None:
        self._db_path = db_path
        self._signals: list[Signal] = []

    def publish(self, signal: Signal) -> bool:
        self._signals.append(signal)
        # schema.md intentionally does not include expiry_seconds; the DB row
        # is an immutable signal log, while expiry remains runtime state.
        return log_signal(
            self._db_path,
            timestamp=signal.issued_at,
            pair=signal.pair,
            source=signal.source,
            structure_class=signal.structure_class.value,
            direction=signal.direction.value,
            price=signal.price,
            atr=signal.atr,
            atr_ratio=signal.atr_ratio,
            spread=signal.spread,
        )

    def get_active_signals(self, pair: str, now: datetime | None = None) -> list[Signal]:
        current = now or datetime.now(UTC)
        if current.tzinfo is None:
            current = current.replace(tzinfo=UTC)
        current = current.astimezone(UTC)

        self._signals = [signal for signal in self._signals if signal.is_active(current)]
        return [
            signal
            for signal in self._signals
            if signal.pair == pair and signal.is_active(current)
        ]
