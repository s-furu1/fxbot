from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


class ConfigError(RuntimeError):
    """Raised when runtime configuration is unsafe or inconsistent."""


REQUIRED_ENV_VARS = (
    "FXBOT_MODE",
    "OANDA_ENV",
    "OANDA_API_KEY",
    "OANDA_ACCOUNT_ID",
    "FXBOT_EXPECTED_MODE",
    "FXBOT_EXPECTED_ACCOUNT_ID",
    "FXBOT_DB_ENV",
    "TZ",
    "LOG_LEVEL",
    "DRY_RUN",
)

VALID_MODES = frozenset({"practice", "live"})
DB_PATH = Path("/data/trades.db")
HEARTBEAT_PATH = Path(os.getenv("HEARTBEAT_PATH", "/tmp/fxbot_heartbeat"))


@dataclass(frozen=True)
class Config:
    mode: str
    oanda_env: str
    oanda_api_key: str
    oanda_account_id: str
    expected_mode: str
    expected_account_id: str
    db_env: str
    slack_webhook_url: str
    tz: str
    log_level: str
    dry_run: bool
    db_path: Path = DB_PATH
    heartbeat_path: Path = HEARTBEAT_PATH


def _parse_bool(value: str, *, name: str) -> bool:
    normalized = value.strip().lower()
    if normalized == "true":
        return True
    if normalized == "false":
        return False
    raise ConfigError(f"{name} must be true or false")


def load_config() -> Config:
    load_dotenv()

    missing = [name for name in REQUIRED_ENV_VARS if not os.getenv(name)]
    if missing:
        raise ConfigError(f"missing required environment variables: {', '.join(missing)}")

    dry_run = _parse_bool(os.environ["DRY_RUN"], name="DRY_RUN")
    if not dry_run:
        raise ConfigError("DRY_RUN=false is not supported in Phase 1")

    return Config(
        mode=os.environ["FXBOT_MODE"],
        oanda_env=os.environ["OANDA_ENV"],
        oanda_api_key=os.environ["OANDA_API_KEY"],
        oanda_account_id=os.environ["OANDA_ACCOUNT_ID"],
        expected_mode=os.environ["FXBOT_EXPECTED_MODE"],
        expected_account_id=os.environ["FXBOT_EXPECTED_ACCOUNT_ID"],
        db_env=os.environ["FXBOT_DB_ENV"],
        slack_webhook_url=os.getenv("SLACK_WEBHOOK_URL", ""),
        tz=os.environ["TZ"],
        log_level=os.environ["LOG_LEVEL"],
        dry_run=dry_run,
        db_path=Path(os.getenv("DB_PATH", str(DB_PATH))),
        heartbeat_path=Path(os.getenv("HEARTBEAT_PATH", str(HEARTBEAT_PATH))),
    )
