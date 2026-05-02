from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum


class StructureClass(StrEnum):
    VOLATILITY = "volatility"
    FLOW = "flow"
    REVERSION = "reversion"


class Direction(StrEnum):
    BUY = "buy"
    SELL = "sell"


@dataclass(frozen=True)
class Signal:
    pair: str
    direction: Direction | str
    source: str
    structure_class: StructureClass | str
    issued_at: datetime
    atr: float
    atr_ratio: float
    spread: float
    price: float
    expiry_seconds: int = 60

    def __post_init__(self) -> None:
        direction = Direction(self.direction)
        structure_class = StructureClass(self.structure_class)
        issued_at = self.issued_at
        if issued_at.tzinfo is None:
            issued_at = issued_at.replace(tzinfo=UTC)

        object.__setattr__(self, "direction", direction)
        object.__setattr__(self, "structure_class", structure_class)
        object.__setattr__(self, "issued_at", issued_at.astimezone(UTC))

    @property
    def expires_at(self) -> datetime:
        return self.issued_at + timedelta(seconds=self.expiry_seconds)

    def is_active(self, now: datetime) -> bool:
        current = now if now.tzinfo is not None else now.replace(tzinfo=UTC)
        return current.astimezone(UTC) <= self.expires_at

    def is_expired(self, now: datetime) -> bool:
        return not self.is_active(now)


class Strategy(ABC):
    source: str
    structure_class: StructureClass

    @abstractmethod
    def generate_signals(self, now: datetime) -> list[Signal]:
        """Return zero or more signals for the current evaluation tick."""
