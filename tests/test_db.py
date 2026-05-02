from __future__ import annotations

import sqlite3

from fxbot.db import init_db, log_entry_rejection


def test_init_db_creates_entry_rejections_schema(tmp_path):
    db_path = tmp_path / "trades.db"

    init_db(db_path)

    with sqlite3.connect(db_path) as conn:
        columns = [
            row[1]
            for row in conn.execute("PRAGMA table_info(entry_rejections)").fetchall()
        ]

    assert columns == [
        "id",
        "timestamp",
        "pair",
        "direction",
        "reason",
        "spread",
        "spread_threshold",
        "atr",
        "atr_ratio",
        "confluence_kind",
        "agreed",
        "classes",
        "extra",
    ]


def test_log_entry_rejection_only_when_db_initialized(tmp_path):
    missing_db = tmp_path / "missing.db"
    assert not log_entry_rejection(
        missing_db,
        pair="SYSTEM",
        direction="none",
        reason="env_mismatch",
    )

    init_db(missing_db)
    assert log_entry_rejection(
        missing_db,
        pair="SYSTEM",
        direction="none",
        reason="env_mismatch",
    )

    with sqlite3.connect(missing_db) as conn:
        row = conn.execute("SELECT pair, direction, reason FROM entry_rejections").fetchone()

    assert row == ("SYSTEM", "none", "env_mismatch")
