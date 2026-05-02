from __future__ import annotations

import sqlite3

from fxbot import main as main_module
from fxbot.db import init_db


class FakeOandaReadOnlyClient:
    account_summary = {"id": "101-001-12345678-001"}
    open_positions = []
    calls = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs

    def get_account_summary(self):
        self.calls.append("get_account_summary")
        return self.account_summary

    def list_open_positions(self):
        self.calls.append("list_open_positions")
        return self.open_positions


def _valid_env(monkeypatch):
    values = {
        "FXBOT_MODE": "practice",
        "OANDA_ENV": "practice",
        "OANDA_API_KEY": "dummy",
        "OANDA_ACCOUNT_ID": "101-001-12345678-001",
        "FXBOT_EXPECTED_MODE": "practice",
        "FXBOT_EXPECTED_ACCOUNT_ID": "101-001-12345678-001",
        "FXBOT_DB_ENV": "practice",
        "TZ": "UTC",
        "LOG_LEVEL": "INFO",
        "DRY_RUN": "true",
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)


def test_check_only_runs_startup_before_db_init(monkeypatch, tmp_path):
    _valid_env(monkeypatch)
    heartbeat_path = tmp_path / "heartbeat"
    db_path = tmp_path / "trades.db"
    events = []

    monkeypatch.setattr(main_module, "DB_PATH", main_module.DB_PATH)
    monkeypatch.setenv("DB_PATH", str(db_path))
    monkeypatch.setenv("HEARTBEAT_PATH", str(heartbeat_path))

    def fake_startup_checks(client, path):
        events.append(("startup", path))

    def fake_init_db(path):
        events.append(("init_db", path))

    monkeypatch.setattr(main_module, "run_startup_checks", fake_startup_checks)
    monkeypatch.setattr(main_module, "init_db", fake_init_db)

    assert main_module.main(["--check-only"]) == 0
    assert events[0] == ("startup", main_module.DB_PATH)
    assert events[1] == ("init_db", db_path)
    assert heartbeat_path.exists()


def test_config_error_records_env_mismatch_only_with_initialized_db(monkeypatch, tmp_path):
    _valid_env(monkeypatch)
    db_path = tmp_path / "trades.db"
    init_db(db_path)
    monkeypatch.setenv("DB_PATH", str(db_path))
    monkeypatch.setenv("FXBOT_EXPECTED_ACCOUNT_ID", "different")

    assert main_module.main(["--check-only"]) == 2

    with sqlite3.connect(db_path) as conn:
        row = conn.execute("SELECT reason FROM entry_rejections").fetchone()

    assert row == ("env_mismatch",)


def test_config_error_does_not_create_db_for_rejection(monkeypatch, tmp_path):
    _valid_env(monkeypatch)
    db_path = tmp_path / "trades.db"
    monkeypatch.setenv("DB_PATH", str(db_path))
    monkeypatch.setenv("FXBOT_EXPECTED_ACCOUNT_ID", "different")

    assert main_module.main(["--check-only"]) == 2
    assert not db_path.exists()


def test_check_only_uses_account_summary_and_open_positions(monkeypatch, tmp_path):
    _valid_env(monkeypatch)
    monkeypatch.setenv("DB_PATH", str(tmp_path / "trades.db"))
    monkeypatch.setenv("HEARTBEAT_PATH", str(tmp_path / "heartbeat"))
    FakeOandaReadOnlyClient.account_summary = {"id": "101-001-12345678-001"}
    FakeOandaReadOnlyClient.open_positions = []
    FakeOandaReadOnlyClient.calls = []
    monkeypatch.setattr(main_module, "OandaReadOnlyClient", FakeOandaReadOnlyClient)

    assert main_module.main(["--check-only"]) == 0
    assert FakeOandaReadOnlyClient.calls == [
        "get_account_summary",
        "list_open_positions",
    ]


def test_check_only_rejects_existing_open_positions(monkeypatch, tmp_path):
    _valid_env(monkeypatch)
    db_path = tmp_path / "trades.db"
    monkeypatch.setenv("DB_PATH", str(db_path))
    FakeOandaReadOnlyClient.account_summary = {"id": "101-001-12345678-001"}
    FakeOandaReadOnlyClient.open_positions = [{"instrument": "EUR_USD"}]
    FakeOandaReadOnlyClient.calls = []
    monkeypatch.setattr(main_module, "OandaReadOnlyClient", FakeOandaReadOnlyClient)

    assert main_module.main(["--check-only"]) == 2
    assert FakeOandaReadOnlyClient.calls == [
        "get_account_summary",
        "list_open_positions",
    ]
    assert not db_path.exists()
