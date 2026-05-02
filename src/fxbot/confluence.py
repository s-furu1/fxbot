from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

from fxbot.strategies.base import Direction, Signal, StructureClass


class ConfluenceKind(StrEnum):
    CROSS_CLASS = "cross-class"
    INTRACLASS_ONLY = "intraclass_only"
    CONFLICTING_SIGNALS = "conflicting_signals"
    NO_CONFLUENCE = "no_confluence"


@dataclass(frozen=True)
class ConfluenceResult:
    pair: str
    direction: str | None
    kind: ConfluenceKind
    signal_count: int
    classes: tuple[str, ...]
    agreed: tuple[str, ...]
    first_signal_time: datetime | None
    last_signal_time: datetime | None
    atr: float | None
    atr_ratio: float | None
    spread: float | None

    @property
    def is_entry_candidate(self) -> bool:
        return self.kind == ConfluenceKind.CROSS_CLASS


def evaluate_confluence(
    pair: str,
    signals: list[Signal],
    now: datetime | None = None,
) -> ConfluenceResult:
    current = None
    if now is not None:
        current = now if now.tzinfo is not None else now.replace(tzinfo=UTC)
        current = current.astimezone(UTC)

    active_signals = [
        signal
        for signal in signals
        if signal.pair == pair and (current is None or not signal.is_expired(current))
    ]
    if not active_signals:
        return _empty_result(pair)

    cross_class: dict[Direction, list[Signal]] = {}
    intraclass: dict[Direction, list[Signal]] = {}

    for direction in Direction:
        directional = [signal for signal in active_signals if signal.direction == direction]
        if len({signal.structure_class for signal in directional}) >= 2:
            cross_class[direction] = directional
            continue

        intraclass_group = _best_intraclass_group(directional)
        if intraclass_group:
            intraclass[direction] = intraclass_group

    if Direction.BUY in cross_class and Direction.SELL in cross_class:
        return _result(
            pair=pair,
            direction=None,
            kind=ConfluenceKind.CONFLICTING_SIGNALS,
            signals=cross_class[Direction.BUY] + cross_class[Direction.SELL],
        )

    if len(cross_class) == 1:
        direction, agreed_signals = next(iter(cross_class.items()))
        return _result(
            pair=pair,
            direction=direction.value,
            kind=ConfluenceKind.CROSS_CLASS,
            signals=agreed_signals,
        )

    if intraclass:
        direction, agreed_signals = max(
            intraclass.items(),
            key=lambda item: (len(item[1]), item[1][-1].issued_at),
        )
        return _result(
            pair=pair,
            direction=direction.value,
            kind=ConfluenceKind.INTRACLASS_ONLY,
            signals=agreed_signals,
        )

    return _empty_result(pair)


def _best_intraclass_group(signals: list[Signal]) -> list[Signal]:
    groups: dict[StructureClass, list[Signal]] = {}
    for signal in signals:
        groups.setdefault(signal.structure_class, []).append(signal)

    candidates = [
        group
        for group in groups.values()
        if len({signal.source for signal in group}) >= 2
    ]
    if not candidates:
        return []
    return max(candidates, key=lambda group: (len(group), group[-1].issued_at))


def _result(
    *,
    pair: str,
    direction: str | None,
    kind: ConfluenceKind,
    signals: list[Signal],
) -> ConfluenceResult:
    ordered = sorted(signals, key=lambda signal: signal.issued_at)
    latest = ordered[-1]
    return ConfluenceResult(
        pair=pair,
        direction=direction,
        kind=kind,
        signal_count=len(ordered),
        classes=tuple(sorted({signal.structure_class.value for signal in ordered})),
        agreed=tuple(sorted({signal.source for signal in ordered})),
        first_signal_time=ordered[0].issued_at,
        last_signal_time=latest.issued_at,
        atr=latest.atr,
        atr_ratio=latest.atr_ratio,
        spread=latest.spread,
    )


def _empty_result(pair: str) -> ConfluenceResult:
    return ConfluenceResult(
        pair=pair,
        direction=None,
        kind=ConfluenceKind.NO_CONFLUENCE,
        signal_count=0,
        classes=(),
        agreed=(),
        first_signal_time=None,
        last_signal_time=None,
        atr=None,
        atr_ratio=None,
        spread=None,
    )
