from __future__ import annotations

from pathlib import Path

import pytest

from fxbot.config import ConfigError
from fxbot.startup_checks import run_startup_checks


class FakeClient:
    def __init__(self, account_id="101-001-12345678-001", positions=None):
        self.account_id = account_id
        self.positions = positions if positions is not None else []

    def get_account_summary(self):
        return {"id": self.account_id}

    def list_open_positions(self):
        return self.positions


def valid_env():
    return {
        "FXBOT_MODE": "practice",
        "OANDA_ENV": "practice",
        "OANDA_ACCOUNT_ID": "101-001-12345678-001",
        "FXBOT_EXPECTED_MODE": "practice",
        "FXBOT_EXPECTED_ACCOUNT_ID": "101-001-12345678-001",
        "FXBOT_DB_ENV": "practice",
        "DRY_RUN": "true",
    }


def test_startup_checks_pass_for_consistent_dry_run_env():
    run_startup_checks(FakeClient(), Path("/data/trades.db"), env=valid_env())


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("FXBOT_EXPECTED_MODE", "live"),
        ("FXBOT_EXPECTED_ACCOUNT_ID", "different"),
        ("FXBOT_DB_ENV", "live"),
        ("DRY_RUN", "false"),
    ],
)
def test_startup_checks_reject_env_mismatch(key, value):
    env = valid_env()
    env[key] = value

    with pytest.raises(ConfigError):
        run_startup_checks(FakeClient(), Path("/data/trades.db"), env=env)


def test_startup_checks_reject_open_positions():
    with pytest.raises(ConfigError):
        run_startup_checks(
            FakeClient(positions=[{"instrument": "EUR_USD"}]),
            Path("/data/trades.db"),
            env=valid_env(),
        )


def test_startup_checks_reject_wrong_db_path():
    with pytest.raises(ConfigError):
        run_startup_checks(FakeClient(), Path("/tmp/trades.db"), env=valid_env())
