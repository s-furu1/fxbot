from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS signals (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp       TEXT    NOT NULL,
    pair            TEXT    NOT NULL,
    source          TEXT    NOT NULL,
    structure_class TEXT    NOT NULL,
    direction       TEXT    NOT NULL,
    price           REAL    NOT NULL,
    atr             REAL    NOT NULL,
    atr_ratio       REAL    NOT NULL,
    spread          REAL    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_signals_pair_ts ON signals(pair, timestamp);
CREATE INDEX IF NOT EXISTS idx_signals_source ON signals(source);

CREATE TABLE IF NOT EXISTS opens (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_id            TEXT    NOT NULL UNIQUE,
    pair                TEXT    NOT NULL,
    direction           TEXT    NOT NULL,
    units               INTEGER NOT NULL,
    first_signal_time   TEXT    NOT NULL,
    last_signal_time    TEXT    NOT NULL,
    entry_time          TEXT    NOT NULL,
    entry_price         REAL    NOT NULL,
    atr                 REAL    NOT NULL,
    atr_ratio           REAL    NOT NULL,
    spread              REAL    NOT NULL,
    risk_ratio          REAL    NOT NULL,
    risk_amount         REAL    NOT NULL,
    sl_price            REAL    NOT NULL,
    tp_price            REAL    NOT NULL,
    confluence_type     TEXT    NOT NULL,
    signal_count        INTEGER NOT NULL,
    classes             TEXT    NOT NULL,
    strategies          TEXT    NOT NULL,
    response            TEXT
);
CREATE INDEX IF NOT EXISTS idx_opens_trade_id ON opens(trade_id);
CREATE INDEX IF NOT EXISTS idx_opens_entry_time ON opens(entry_time);

CREATE TABLE IF NOT EXISTS closes (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_id        TEXT    NOT NULL UNIQUE,
    exit_time       TEXT    NOT NULL,
    exit_price      REAL    NOT NULL,
    exit_reason     TEXT    NOT NULL,
    pnl             REAL    NOT NULL,
    actual_rr       REAL    NOT NULL,
    mfe             REAL    NOT NULL,
    mae             REAL    NOT NULL,
    holding_seconds INTEGER NOT NULL,
    FOREIGN KEY (trade_id) REFERENCES opens(trade_id)
);
CREATE INDEX IF NOT EXISTS idx_closes_trade_id ON closes(trade_id);
CREATE INDEX IF NOT EXISTS idx_closes_exit_time ON closes(exit_time);

CREATE TABLE IF NOT EXISTS latency (
    id                       INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_id                 TEXT    NOT NULL UNIQUE,
    confluence_to_fill_ms    INTEGER NOT NULL,
    first_signal_to_fill_ms  INTEGER NOT NULL,
    FOREIGN KEY (trade_id) REFERENCES opens(trade_id)
);

CREATE TABLE IF NOT EXISTS position_tracking (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_id    TEXT    NOT NULL,
    timestamp   TEXT    NOT NULL,
    bid         REAL    NOT NULL,
    ask         REAL    NOT NULL,
    mid         REAL    NOT NULL,
    FOREIGN KEY (trade_id) REFERENCES opens(trade_id)
);
CREATE INDEX IF NOT EXISTS idx_position_tracking_trade_id ON position_tracking(trade_id);
CREATE INDEX IF NOT EXISTS idx_position_tracking_ts ON position_tracking(timestamp);

CREATE TABLE IF NOT EXISTS baseline_solo (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp       TEXT    NOT NULL,
    pair            TEXT    NOT NULL,
    source          TEXT    NOT NULL,
    structure_class TEXT    NOT NULL,
    direction       TEXT    NOT NULL,
    price           REAL    NOT NULL,
    atr             REAL    NOT NULL,
    atr_ratio       REAL    NOT NULL,
    spread          REAL    NOT NULL,
    virtual_exit_time   TEXT,
    virtual_exit_price  REAL,
    virtual_pnl         REAL,
    virtual_rr          REAL,
    virtual_mfe         REAL,
    virtual_mae         REAL,
    virtual_exit_reason TEXT
);
CREATE INDEX IF NOT EXISTS idx_baseline_solo_ts ON baseline_solo(timestamp);

CREATE TABLE IF NOT EXISTS baseline_intraclass (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp       TEXT    NOT NULL,
    pair            TEXT    NOT NULL,
    structure_class TEXT    NOT NULL,
    direction       TEXT    NOT NULL,
    strategies      TEXT    NOT NULL,
    price           REAL    NOT NULL,
    atr             REAL    NOT NULL,
    atr_ratio       REAL    NOT NULL,
    spread          REAL    NOT NULL,
    virtual_exit_time   TEXT,
    virtual_exit_price  REAL,
    virtual_pnl         REAL,
    virtual_rr          REAL,
    virtual_mfe         REAL,
    virtual_mae         REAL,
    virtual_exit_reason TEXT
);
CREATE INDEX IF NOT EXISTS idx_baseline_intraclass_ts ON baseline_intraclass(timestamp);

CREATE TABLE IF NOT EXISTS baseline_random (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp       TEXT    NOT NULL,
    pair            TEXT    NOT NULL,
    direction       TEXT    NOT NULL,
    price           REAL    NOT NULL,
    atr             REAL    NOT NULL,
    atr_ratio       REAL    NOT NULL,
    spread          REAL    NOT NULL,
    virtual_exit_time   TEXT,
    virtual_exit_price  REAL,
    virtual_pnl         REAL,
    virtual_rr          REAL,
    virtual_mfe         REAL,
    virtual_mae         REAL,
    virtual_exit_reason TEXT,
    paired_trade_id     TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_baseline_random_ts ON baseline_random(timestamp);
CREATE INDEX IF NOT EXISTS idx_baseline_random_paired ON baseline_random(paired_trade_id);

CREATE TABLE IF NOT EXISTS currency_exposure_snapshots (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp   TEXT    NOT NULL,
    currency    TEXT    NOT NULL,
    net_ratio   REAL    NOT NULL,
    equity      REAL    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_currency_exposure_ts ON currency_exposure_snapshots(timestamp);

CREATE TABLE IF NOT EXISTS spread_history (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp   TEXT    NOT NULL,
    pair        TEXT    NOT NULL,
    bid         REAL    NOT NULL,
    ask         REAL    NOT NULL,
    spread      REAL    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_spread_history_pair_ts ON spread_history(pair, timestamp);

CREATE TABLE IF NOT EXISTS entry_rejections (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp        TEXT    NOT NULL,
    pair             TEXT    NOT NULL,
    direction        TEXT    NOT NULL,
    reason           TEXT    NOT NULL,
    spread           REAL,
    spread_threshold REAL,
    atr              REAL,
    atr_ratio        REAL,
    confluence_kind  TEXT,
    agreed           TEXT,
    classes          TEXT,
    extra            TEXT
);
CREATE INDEX IF NOT EXISTS idx_entry_rejections_ts ON entry_rejections(timestamp);
CREATE INDEX IF NOT EXISTS idx_entry_rejections_reason ON entry_rejections(reason);
CREATE INDEX IF NOT EXISTS idx_entry_rejections_pair ON entry_rejections(pair);
CREATE INDEX IF NOT EXISTS idx_entry_rejections_pair_reason ON entry_rejections(pair, reason);
"""


def connect(db_path: Path) -> sqlite3.Connection:
    return sqlite3.connect(db_path)


def init_db(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with connect(db_path) as conn:
        conn.executescript(SCHEMA_SQL)


def has_entry_rejections_table(db_path: Path) -> bool:
    if not db_path.exists():
        return False
    try:
        with connect(db_path) as conn:
            row = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='entry_rejections'"
            ).fetchone()
    except sqlite3.Error:
        return False
    return row is not None


def has_spread_history_table(db_path: Path) -> bool:
    if not db_path.exists():
        return False
    try:
        with connect(db_path) as conn:
            row = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='spread_history'"
            ).fetchone()
    except sqlite3.Error:
        return False
    return row is not None


def log_entry_rejection(
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
    if not has_entry_rejections_table(db_path):
        return False

    try:
        with connect(db_path) as conn:
            conn.execute(
                """
                INSERT INTO entry_rejections (
                    timestamp, pair, direction, reason, spread, spread_threshold,
                    atr, atr_ratio, confluence_kind, agreed, classes, extra
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    datetime.now(UTC).isoformat(),
                    pair,
                    direction,
                    reason,
                    spread,
                    spread_threshold,
                    atr,
                    atr_ratio,
                    confluence_kind,
                    agreed,
                    classes,
                    json.dumps(extra or {}, sort_keys=True),
                ),
            )
    except sqlite3.Error:
        return False
    return True


def log_spread_history(
    db_path: Path,
    *,
    pair: str,
    bid: float,
    ask: float,
    timestamp: datetime | None = None,
) -> bool:
    if not has_spread_history_table(db_path):
        return False

    observed_at = timestamp or datetime.now(UTC)
    spread = ask - bid
    try:
        with connect(db_path) as conn:
            conn.execute(
                """
                INSERT INTO spread_history (
                    timestamp, pair, bid, ask, spread
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (observed_at.isoformat(), pair, bid, ask, spread),
            )
    except sqlite3.Error:
        return False
    return True


def query_spreads(db_path: Path, *, pair: str, since: datetime) -> list[float]:
    if not has_spread_history_table(db_path):
        return []

    try:
        with connect(db_path) as conn:
            rows = conn.execute(
                """
                SELECT spread FROM spread_history
                WHERE pair = ? AND timestamp >= ?
                ORDER BY timestamp ASC
                """,
                (pair, since.isoformat()),
            ).fetchall()
    except sqlite3.Error:
        return []
    return [float(row[0]) for row in rows]
